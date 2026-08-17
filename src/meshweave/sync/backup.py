"""Backup diario: pg_dump completo de la nube (contenedor supabase-db).

- El password se toma de DPAPI (meshweave.secrets), nunca de config.json.
- Retención configurable (backup_retention_days, default 7).
- Historial en logs/backup_runs.jsonl + alerta por email si falla.
"""
from __future__ import annotations

import json
import subprocess as _sp
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from meshweave.config import (
    BACKUP_RUNS_LOG,
    BACKUPS_DIR,
    load_config,
    read_env_file,
)
from meshweave.paths import logs_dir
from meshweave.process_runner import CREATE_NO_WINDOW
from meshweave.secrets import SecretStore
from meshweave.sync.alerts import maybe_send_failure_alert
from meshweave.sync.engine import now_iso


def run_backup(
    cfg: dict[str, Any] | None = None,
    emit: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Dump completo de la nube vía pg_dump + retención. Devuelve el resultado."""
    cfg = cfg or load_config()
    emit = emit or (lambda msg, lvl: None)
    started = now_iso()
    t0 = time.time()
    result: dict[str, Any] = {
        "started_at": started, "finished_at": None, "duration_s": 0,
        "status": "error", "file": None, "size_bytes": None, "error": None,
    }
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        host = cfg.get("cloud_db_host", "")
        user = cfg.get("cloud_db_user", "")
        if not host or not user:
            raise RuntimeError("Faltan cloud_db_host / cloud_db_user en la configuración.")
        password = SecretStore().get("cloud_db_password")
        if not password:
            raise RuntimeError("No hay contraseña de la nube en el almacén DPAPI.")
        port = cfg.get("cloud_db_port", 5432)
        db = cfg.get("cloud_db_name", "postgres")
        container = cfg.get("backup_container", "supabase-db")
        dump_in = "/tmp/cloud-backup.dump"
        url = f"postgresql://{user}@{host}:{port}/{db}"
        timeout = int(cfg.get("backup_timeout_seconds", 300))

        def _run(args: list[str]):
            return _sp.run(args, capture_output=True, text=True, timeout=timeout,
                           creationflags=CREATE_NO_WINDOW)

        emit("Backup de la nube: pg_dump vía supabase-db…", "info")
        r = _run(["docker", "exec", "-e", f"PGPASSWORD={password}", container,
                  "pg_dump", url, "-Fc", "--no-owner", "--no-privileges", "-f", dump_in])
        if r.returncode != 0:
            raise RuntimeError(f"pg_dump falló: {(r.stderr or r.stdout).strip()}")
        date = datetime.now().astimezone().strftime("%Y%m%d")
        outfile = BACKUPS_DIR / f"cloud-{date}.dump"
        r = _run(["docker", "cp", f"{container}:{dump_in}", str(outfile)])
        if r.returncode != 0:
            raise RuntimeError(f"docker cp falló: {(r.stderr or r.stdout).strip()}")
        _run(["docker", "exec", container, "rm", "-f", dump_in])

        size = outfile.stat().st_size if outfile.exists() else 0
        result.update(status="ok", file=outfile.name, size_bytes=size,
                      duration_s=round(time.time() - t0, 1), finished_at=now_iso())
        emit(f"Backup OK: {outfile.name} ({size / 1024 / 1024:.2f} MB)", "ok")

        # Retención: borra dumps viejos (config backup_retention_days)
        retention = int(cfg.get("backup_retention_days", 7))
        cutoff = time.time() - retention * 86400
        removed: list[str] = []
        for f in BACKUPS_DIR.glob("cloud-*.dump"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed.append(f.name)
            except OSError:
                pass
        if removed:
            emit(f"Retención ({retention} días): eliminados {len(removed)} dump(s) viejos", "info")
    except Exception as e:  # noqa: BLE001
        result["finished_at"] = now_iso()
        result["duration_s"] = round(time.time() - t0, 1)
        result["error"] = str(e)
        emit(f"ERROR backup: {e}", "error")
    finally:
        try:
            logs_dir().mkdir(parents=True, exist_ok=True)
            with open(BACKUP_RUNS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass
    if result.get("status") != "ok":
        alert_res = maybe_send_failure_alert(cfg, "backup", result)
        if alert_res:
            emit(
                f"Alerta de fallo: {alert_res.get('status')} — {alert_res.get('reason', '')}",
                "warn" if alert_res.get("status") == "error" else "info",
            )
    return result


def _resolve_dump_path(raw: str) -> Path:
    """Convierte el argumento de restore en una ruta absoluta del dump.

    Acepta: nombre simple ("cloud-20260816.dump" → se resuelve contra
    backups/), ruta Windows (C:\\...) o formato MSYS/Git Bash
    ("/c/ProgramData/..." → C:\\...). Sin esta normalización, un nombre
    simple se resolvía contra el CWD del proceso, y una ruta "/c/..." se
    interpretaba como "\\c\\..." (raíz del drive actual + carpeta literal
    "c"), produciendo errores confusos como "\\c\\ProgramData\\...".
    """
    p = Path(raw)
    if not p.anchor:
        # Nombre simple (GUI combo / CLI): siempre dentro de backups/.
        return BACKUPS_DIR / p
    if (not p.drive and p.anchor in ("\\", "/") and len(p.parts) >= 2
            and len(p.parts[1]) == 1 and p.parts[1].isalpha()):
        return Path(f"{p.parts[1].upper()}:\\").joinpath(*p.parts[2:])
    if not p.drive and len(p.parts) >= 2 and len(p.parts[1]) == 1 and p.parts[1].isalpha():
        # "/c/ProgramData/..." o "\\c\\ProgramData/..." → "C:\\ProgramData\..."
        return Path(f"{p.parts[1].upper()}:\\").joinpath(*p.parts[2:])
    return p


def restore_dump(
    cfg: dict[str, Any] | None = None,
    dump_file: str | None = None,
    emit: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Restaura un dump (formato custom) de la nube en la DB local (Docker).

    Uso típico: PC nueva con la DB local vacía → traer los datos desde un
    dump de backups/. Sin `--clean`: las tablas existentes se conservan
    ("already exists" benigno) y se cargan las que falten — evita romper la
    publicación realtime del stack local. Al final resetea las secuencias.
    """
    cfg = cfg or load_config()
    emit = emit or (lambda msg, lvl: None)
    started = now_iso()
    t0 = time.time()
    result: dict[str, Any] = {
        "started_at": started, "finished_at": None, "duration_s": 0,
        "status": "error", "file": None, "error": None,
    }
    try:
        if not dump_file:
            dumps = sorted(BACKUPS_DIR.glob("cloud-*.dump"))
            if not dumps:
                raise RuntimeError("No hay dumps en el directorio de backups.")
            dump_file = str(dumps[-1])
        dump = _resolve_dump_path(dump_file)
        if not dump.exists():
            raise RuntimeError(f"El dump no existe: {dump}")

        env = read_env_file(Path(cfg["supabase_env"]))
        user = env.get("POSTGRES_USER", "postgres")
        password = env.get("POSTGRES_PASSWORD", "")
        db = env.get("POSTGRES_DB", "postgres")
        container = cfg.get("backup_container", "supabase-db")
        if not env:
            raise RuntimeError(f"No se pudo leer el .env local: {cfg['supabase_env']}")

        timeout = int(cfg.get("backup_timeout_seconds", 300))

        def _run(args: list[str]):
            return _sp.run(args, capture_output=True, text=True, timeout=timeout,
                           creationflags=CREATE_NO_WINDOW)

        dump_in = "/tmp/restore.dump"
        emit(f"Restaurando {dump.name} → DB local ({db})…", "info")
        r = _run(["docker", "cp", str(dump), f"{container}:{dump_in}"])
        if r.returncode != 0:
            raise RuntimeError(f"docker cp falló: {(r.stderr or r.stdout).strip()}")

        r = _run(["docker", "exec", "-e", f"PGPASSWORD={password}", container,
                  "pg_restore", "-Fc", "--no-owner", "--no-privileges",
                  "-U", user, "-d", db, dump_in])
        err_text = (r.stderr or r.stdout or "")
        if r.returncode != 0:
            # El exit 1 puede venir de errores benignos ("already exists" o
            # permisos de extensiones como vault/"SET log_min_messages")
            # mientras los datos sí se cargan. Los mostramos como aviso y la
            # verificación final se hace por CONTENIDO real de la DB.
            benign = all(
                w in err_text.lower()
                for w in ("already exists", "permission denied")
            ) or "permission denied" in err_text.lower()
            if not benign and "already exists" not in err_text.lower():
                _run(["docker", "exec", container, "rm", "-f", dump_in])
                raise RuntimeError(f"pg_restore falló: {err_text.strip()[:800]}")
            emit("pg_restore reportó avisos (ya existentes/permisos de extensiones) "
                 "— se verifica el contenido real.", "warn")

        # Verificación por contenido: al menos una tabla con datos en public.
        v = _run(["docker", "exec", "-e", f"PGPASSWORD={password}", container,
                  "psql", "-U", user, "-d", db, "-tAc",
                  "select count(*) from pg_tables where schemaname='public'"])
        try:
            table_count = int(v.stdout.strip() or "0")
        except ValueError:
            table_count = 0
        if table_count == 0:
            _run(["docker", "exec", container, "rm", "-f", dump_in])
            raise RuntimeError(
                f"La restauración no cargó tablas. pg_restore: {err_text.strip()[:400]}"
            )

        # Reset de secuencias para no colisionar con inserts nuevos.
        n_seq = _reset_sequences(cfg, emit)
        _run(["docker", "exec", container, "rm", "-f", dump_in])

        result.update(status="ok", file=dump.name,
                      duration_s=round(time.time() - t0, 1), finished_at=now_iso())
        emit(f"Restauración OK ({dump.name}) — {table_count} tablas, "
             f"{n_seq} secuencia(s) ajustada(s).", "ok")
    except Exception as e:  # noqa: BLE001
        result["finished_at"] = now_iso()
        result["duration_s"] = round(time.time() - t0, 1)
        result["error"] = str(e)
        emit(f"ERROR restauración: {e}", "error")
    finally:
        try:
            logs_dir().mkdir(parents=True, exist_ok=True)
            with open(RESTORE_RUNS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass
    return result


RESTORE_RUNS_LOG = logs_dir() / "restore_runs.jsonl"


def _reset_sequences(cfg: dict[str, Any], emit: Callable[[str, str], None]) -> int:
    """setval de cada secuencia de public al max(col) de su tabla."""
    from meshweave.sync.engine import _connect, build_local_url

    try:
        url = build_local_url(cfg)
    except Exception as e:  # noqa: BLE001
        emit(f"  (no se pudieron resetear secuencias: {e})", "warn")
        return 0
    n = 0
    try:
        with _connect(url, int(cfg["connect_timeout_seconds"])) as conn, conn.cursor() as cur:
            cur.execute(
                """
                select s.relname as seq, t.relname as tbl, a.attname as col
                from pg_class s
                join pg_depend d
                  on d.objid = s.oid and d.classid = 'pg_class'::regclass
                 and d.refclassid = 'pg_class'::regclass and d.deptype in ('a', 'i')
                join pg_class t on t.oid = d.refobjid
                join pg_attribute a on a.attrelid = t.oid and a.attnum = d.refobjsubid
                join pg_namespace n on n.oid = s.relnamespace
                where s.relkind = 'S' and n.nspname = 'public'
                """
            )
            rows = cur.fetchall()
            for seq, tbl, col in rows:
                cur.execute(
                    f'SELECT setval(\'{seq}\', COALESCE(MAX("{col}"), 1), '
                    f'MAX("{col}") IS NOT NULL) FROM public."{tbl}"'
                )
                n += 1
            conn.commit()
    except Exception as e:  # noqa: BLE001
        emit(f"  (error reseteando secuencias: {e})", "warn")
        return n
    return n


LOG_DIR_JSONL = None  # placeholder reemplazado abajo


def read_backup_runs(limit: int = 8) -> list[dict[str, Any]]:
    """Últimos backups desde logs/backup_runs.jsonl (una por línea)."""
    if not BACKUP_RUNS_LOG.exists():
        return []
    try:
        lines = BACKUP_RUNS_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out
