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
from typing import Any

from meshweave.config import (
    BACKUP_RUNS_LOG,
    BACKUPS_DIR,
    load_config,
)
from meshweave.paths import logs_dir
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
            return _sp.run(args, capture_output=True, text=True, timeout=timeout)

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
