"""Motor de sincronización incremental Docker (local) → Supabase Cloud.

Free-tier friendly:
  - Watermark por tabla basado en `updated_at` (incremental, reanudable).
  - Tablas sin `updated_at` (ingesta, alembic) → full upsert por corrida.
  - Upserts en lotes: INSERT ... ON CONFLICT (pk) DO UPDATE.
  - Throttling: delay + jitter entre lotes, reintentos con backoff exponencial.
  - Política conservadora (backup): NUNCA se borra nada en la nube (superset).
  - Orden de tablas por dependencias FK (padres primero).
  - Lockfile anti-concurrencia; watermark persistido tras cada lote.

Los paths y la config vienen de meshweave.config / meshweave.paths
(datos en %ProgramData%\\Meshweave, secretos en DPAPI).
"""
from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meshweave.config import (
    RUNS_LOG,
    STATE_PATH,
    cloud_db_url,
    load_state,
    read_env_file,
    save_state,
)
from meshweave.paths import logs_dir
from meshweave.sync.alerts import maybe_send_failure_alert, maybe_send_summary

LEVELS = ("debug", "info", "warn", "error")
OK, WARN, ERR = "#22c55e", "#f59e0b", "#ef4444"

_STALE_LOCK_SECONDS = 6 * 3600  # un lock de más de 6 h se considera huérfano


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# Conexión
# ═══════════════════════════════════════════════════════════════════════════

def _connect(url: str, timeout: int):
    import psycopg

    return psycopg.connect(url, connect_timeout=timeout)


def build_local_url(cfg: dict[str, Any]) -> str:
    env = read_env_file(Path(cfg["supabase_env"]))
    host = env.get("POSTGRES_HOST", "localhost")
    # En docker-compose el host es el nombre interno del contenedor ('db');
    # desde el host de Windows se accede por el pooler mapeado a 127.0.0.1.
    if host in ("db", "supabase-db"):
        host = "127.0.0.1"
    port = env.get("POSTGRES_PORT", "5432")
    db = env.get("POSTGRES_DB", "postgres")
    user = env.get("POSTGRES_USER", "postgres")
    # El pooler local (Supavisor) enruta por tenant: el usuario debe llevar
    # el sufijo .<POOLER_TENANT_ID> (p.ej. postgres.local) igual que el backend.
    tenant = env.get("POOLER_TENANT_ID", "").strip()
    if tenant:
        user = f"{user}.{tenant}"
    password = env.get("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def check_connections(cfg: dict[str, Any]) -> dict[str, Any]:
    """Prueba de conectividad + tamaño de DB (solo lectura)."""
    local_url = build_local_url(cfg)
    cloud_url = cloud_db_url(cfg)
    timeout = int(cfg["connect_timeout_seconds"])
    out: dict[str, Any] = {}
    for name, url in (("local", local_url), ("cloud", cloud_url)):
        try:
            with _connect(url, timeout) as conn, conn.cursor() as cur:
                cur.execute(
                    "select current_setting('server_version'), "
                    "pg_size_pretty(pg_database_size(current_database()))"
                )
                version, size = cur.fetchone()
                out[name] = {"ok": True, "version": version, "size": size}
        except Exception as e:  # noqa: BLE001 — reportar cualquier error de conexión
            out[name] = {"ok": False, "error": str(e)}
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Lock anti-concurrencia
# ═══════════════════════════════════════════════════════════════════════════

class SyncLock:
    def __init__(self, path: Path):
        self.path = path

    def acquire(self) -> None:
        if self.path.exists():
            age = time.time() - self.path.stat().st_mtime
            if age > _STALE_LOCK_SECONDS:
                self.path.unlink(missing_ok=True)
            else:
                raise RuntimeError(
                    f"Ya hay un sync en curso (lock: {self.path.name}). "
                    "Si es un lock huérfano, bórralo o espera."
                )
        self.path.write_text(f"pid={os.getpid()} started={now_iso()}\n", encoding="utf-8")

    def release(self) -> None:
        self.path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# Introspección de esquema
# ═══════════════════════════════════════════════════════════════════════════

def _introspect(conn, schema: str = "public") -> dict[str, dict[str, Any]]:
    """Por tabla: columnas (orden), pk, si tiene updated_at, FK a qué tablas."""
    from psycopg.rows import dict_row

    tables: dict[str, dict[str, Any]] = {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select c.relname as table_name,
                   coalesce(a.attname, '') as column_name,
                   format_type(a.atttypid, a.atttypmod) as data_type,
                   a.attnotnull
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            left join pg_attribute a
              on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
            where n.nspname = %s and c.relkind = 'r'
            order by c.relname, a.attnum
            """,
            (schema,),
        )
        for row in cur:
            t = tables.setdefault(
                row["table_name"],
                {"columns": [], "types": {}, "pk": [], "fk_parents": set(), "has_updated_at": False},
            )
            if row["column_name"]:
                t["columns"].append(row["column_name"])
                t["types"][row["column_name"]] = row["data_type"]
                if row["column_name"] == "updated_at":
                    t["has_updated_at"] = True

        cur.execute(
            """
            select c.relname as table_name,
                   array_agg(a.attname order by k.ord) as pk_cols
            from pg_index i
            join pg_class c on c.oid = i.indrelid
            join pg_namespace n on n.oid = c.relnamespace
            join unnest(i.indkey) with ordinality k(attnum, ord) on true
            join pg_attribute a on a.attrelid = c.oid and a.attnum = k.attnum
            where i.indisprimary and n.nspname = %s
            group by c.relname, i.indisprimary
            """,
            (schema,),
        )
        for row in cur:
            if row["table_name"] in tables:
                tables[row["table_name"]]["pk"] = list(row["pk_cols"])

        cur.execute(
            """
            select c.relname as table_name, fc.relname as parent
            from pg_constraint con
            join pg_class c on c.oid = con.conrelid
            join pg_namespace n on n.oid = c.relnamespace
            join pg_class fc on fc.oid = con.confrelid
            where con.contype = 'f' and n.nspname = %s
            """,
            (schema,),
        )
        for row in cur:
            t = tables.get(row["table_name"])
            if t is not None:
                t["fk_parents"].add(row["parent"])
    return tables


def topo_order(tables: dict[str, dict[str, Any]], exclude: set[str]) -> list[str]:
    """Padres antes que hijos (Kahn). Los que no tienen FK van primero."""
    names = [n for n in tables if n not in exclude]
    remaining = set(names)
    ordered: list[str] = []
    while remaining:
        ready = sorted(
            n for n in remaining
            if not (tables[n]["fk_parents"] & remaining)
        )
        if not ready:  # ciclo (no debería pasar): romper insertando cualquiera
            ready = [sorted(remaining)[0]]
        ordered.extend(ready)
        remaining -= set(ready)
    return ordered


# ═══════════════════════════════════════════════════════════════════════════
# Motor
# ═══════════════════════════════════════════════════════════════════════════

class SyncEngine:
    def __init__(self, cfg: dict[str, Any], emit: Callable[[str, str], None] | None = None):
        self.cfg = cfg
        self.emit = emit or (lambda msg, level: None)
        self.stats: dict[str, dict[str, int]] = {}
        self.total_rows = 0

    def _log(self, msg: str, level: str = "info") -> None:
        self.emit(msg, level)

    def _sleep_between_batches(self) -> None:
        delay = float(self.cfg["batch_delay_seconds"])
        jitter = random.uniform(0, float(self.cfg["jitter_seconds"]))
        time.sleep(delay + jitter)

    @staticmethod
    def _placeholder(col_type: str):
        from psycopg import sql

        # Casts explícitos para columnas JSON: sin ellos psycopg3 no sabe si
        # serializar como json o jsonb y falla con dicts ("cannot adapt"/"invalid
        # input syntax for type json").
        if col_type == "jsonb":
            return sql.SQL("%s::jsonb")
        if col_type == "json":
            return sql.SQL("%s::json")
        return sql.SQL("%s")

    def _upsert_sql(self, table: str, meta: dict):
        from psycopg import sql

        cols = meta["columns"]
        pk = meta["pk"]
        types = meta.get("types", {})
        non_pk = [c for c in cols if c not in pk]
        insert = sql.SQL("INSERT INTO {t} ({c}) VALUES ({v}) ON CONFLICT ({p})").format(
            t=sql.Identifier("public", table),
            c=sql.SQL(", ").join(map(sql.Identifier, cols)),
            v=sql.SQL(", ").join(self._placeholder(types.get(c, "")) for c in cols),
            p=sql.SQL(", ").join(map(sql.Identifier, pk)),
        )
        if non_pk:
            return insert + sql.SQL(" DO UPDATE SET {u}").format(
                u=sql.SQL(", ").join(
                    sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(col)) for col in non_pk
                )
            )
        # Tablas con una sola columna que ES el pk (p.ej. alembic_version):
        # no hay nada que actualizar, solo insertar si no existe.
        return insert + sql.SQL(" DO NOTHING")

    # ── Corrida completa ──────────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        started = now_iso()
        t0 = time.time()
        state = load_state()
        lock = SyncLock(STATE_PATH.with_name("sync.lock"))
        lock.acquire()
        result: dict[str, Any] = {
            "started_at": started,
            "finished_at": None,
            "duration_s": 0,
            "status": "error",
            "tables": {},
            "total_rows": 0,
            "db_sizes": {},
            "error": None,
        }
        try:
            local_url = build_local_url(self.cfg)
            cloud_url = cloud_db_url(self.cfg)
            timeout = int(self.cfg["connect_timeout_seconds"])

            self._log("Conectando a local… (Docker)", "info")
            with _connect(local_url, timeout) as local, _connect(cloud_url, timeout) as cloud:
                self._log("Conectando a nube… (pooler)", "info")
                self._log_sizes(local, cloud, result)

                tables = _introspect(local)
                exclude = set(self.cfg.get("exclude_tables", []))
                order = topo_order(tables, exclude)
                self._log(
                    f"Tablas a sincronizar: {len(order)} "
                    f"(orden FK: {', '.join(order[:6])}{'…' if len(order) > 6 else ''})",
                    "info",
                )

                for table in order:
                    self._sync_table(local, cloud, state, tables[table], table)

            result["duration_s"] = round(time.time() - t0, 1)
            result["finished_at"] = now_iso()
            errors = sum(self.stats[t]["errors"] for t in self.stats)
            result["status"] = "ok" if errors == 0 else "partial"
            result["tables"] = self.stats
            result["total_rows"] = self.total_rows
            if errors:
                result["error"] = f"{errors} error(es) de lote en la nube (ver meshweave.log)"
            self._log(
                f"Corrida finalizada: {result['status']} | filas procesadas: {self.total_rows} "
                f"| en {result['duration_s']}s",
                "ok" if errors == 0 else "warn",
            )
            alert_res = maybe_send_failure_alert(self.cfg, "sync", result)
            if alert_res:
                self._log(
                    f"Alerta de fallo: {alert_res.get('status')} — {alert_res.get('reason', '')}",
                    "warn" if alert_res.get("status") == "error" else "info",
                )
            summary_res = maybe_send_summary(self.cfg, result)
            if summary_res:
                self._log(
                    f"Resumen diario: {summary_res.get('status')} — {summary_res.get('reason', '')}",
                    "warn" if summary_res.get("status") == "error" else "info",
                )
        except Exception as e:  # noqa: BLE001
            result["finished_at"] = now_iso()
            result["duration_s"] = round(time.time() - t0, 1)
            result["error"] = str(e)
            self._log(f"ERROR: {e}", "error")
        finally:
            lock.release()
            state["last_run"] = {
                "started_at": result["started_at"],
                "finished_at": result["finished_at"],
                "status": result["status"],
                "error": result["error"],
            }
            save_state(state)
            self._append_run(result)
        return result

    # ── Tabla individual ──────────────────────────────────────────────────

    def _sync_table(
        self,
        local,
        cloud,
        state: dict[str, Any],
        meta: dict[str, Any],
        table: str,
    ) -> None:
        from psycopg import sql

        cols = meta["columns"]
        pk = meta["pk"]
        self.stats.setdefault(table, {"inserts": 0, "updates": 0, "rows": 0, "errors": 0})

        if not pk:
            self._log(f"⏭ {table}: sin primary key → se omite", "warn")
            self.stats[table]["errors"] += 1
            return

        has_ts = meta["has_updated_at"]
        full = not has_ts
        if full and table not in set(self.cfg.get("full_sync_tables", [])):
            # Sin updated_at y no marcada: full upsert solo si es chica.
            cur = local.cursor()
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("public", table)))
            n = cur.fetchone()[0]
            cur.close()
            if n > int(self.cfg.get("auto_full_sync_max_rows", 5000)):
                self._log(
                    f"⏭ {table}: sin updated_at y {n} filas (> {self.cfg['auto_full_sync_max_rows']}) "
                    "→ se omite (agrégala a full_sync_tables si debe sincronizar)",
                    "warn",
                )
                self.stats[table]["errors"] += 1
                return
            full = True  # tabla chica sin timestamp → full upsert

        watermark = state["watermarks"].get(table)
        if isinstance(watermark, str):  # formato legacy → resincronizar desde el inicio
            watermark = None
        mode = "FULL" if full else f"incr ({watermark or 'desde el inicio'})"
        self._log(f"▶ {table}: {mode}", "info")

        upsert = self._upsert_sql(table, meta)
        sel_cols = sql.SQL(", ").join(map(sql.Identifier, cols))
        tbl = sql.Identifier("public", table)
        batch = int(self.cfg["batch_size"])
        json_cols = {c for c in cols if meta.get("types", {}).get(c) in ("json", "jsonb")}

        try:
            if full:
                with local.cursor() as cur:
                    cur.execute(sql.SQL("SELECT {} FROM {}").format(sel_cols, tbl))
                    rows = cur.fetchall()
                self._upsert_batches(cloud, upsert, rows, table, cols, json_cols)
                self.stats[table]["rows"] = len(rows)
                self.total_rows += len(rows)
                self._log(f"✓ {table}: {len(rows)} fila(s) (full)", "ok")
            else:
                # Paginación por cursor: WHERE (updated_at, pk...) > (cursor)
                # Evita saltos cuando varias filas comparten updated_at y no
                # provoca bucles infinitos (a diferencia de >= sobre un solo valor).
                pk_ids = [sql.Identifier(c) for c in pk]
                order_sql = sql.SQL("ORDER BY {u} ASC, {p} ASC").format(
                    u=sql.Identifier("updated_at"),
                    p=sql.SQL(", ").join(pk_ids),
                )
                processed = 0
                while True:
                    params: list = [batch]
                    if watermark is None:
                        where = sql.SQL("")
                    else:
                        where = sql.SQL("WHERE ({u}, {p}) > ({vu}, {vp})").format(
                            u=sql.Identifier("updated_at"),
                            p=sql.SQL(", ").join(pk_ids),
                            vu=sql.SQL("%s"),
                            vp=sql.SQL(", ").join(sql.SQL("%s") for _ in pk),
                        )
                        params = [watermark["updated_at"], *watermark["pk"], batch]
                    with local.cursor() as cur:
                        cur.execute(
                            sql.SQL("SELECT {} FROM {} {} {} LIMIT %s").format(
                                sel_cols, tbl, where, order_sql
                            ),
                            params,
                        )
                        rows = cur.fetchall()
                    if not rows:
                        break
                    self._upsert_batches(cloud, upsert, rows, table, cols, json_cols)
                    processed += len(rows)
                    last = rows[-1]
                    watermark = {
                        "updated_at": last[cols.index("updated_at")].isoformat(),
                        "pk": [last[cols.index(c)] for c in pk],
                    }
                    state["watermarks"][table] = watermark
                    save_state(state)  # reanudable tras cada lote
                    self._sleep_between_batches()
                self.stats[table]["rows"] = processed
                self.total_rows += processed
                self._log(f"✓ {table}: {processed} fila(s) (incremental)", "ok")
        except Exception as e:  # noqa: BLE001
            self.stats[table]["errors"] += 1
            self._log(f"✗ {table}: {e}", "error")

    @staticmethod
    def _jsonify(row: tuple, cols: list[str], json_cols: set[str]) -> tuple:
        """Serializa dicts/listas de columnas json/jsonb a texto JSON.

        psycopg3 no adapta dicts de forma confiable dentro de executemany en
        pipeline; pasarlos como string + cast (%s::jsonb) es determinista.
        """
        if not json_cols:
            return row
        return tuple(
            json.dumps(v, ensure_ascii=False, default=str)
            if (col in json_cols and isinstance(v, (dict, list)))
            else v
            for col, v in zip(cols, row, strict=False)
        )

    def _upsert_batches(self, cloud, upsert, rows: list, table: str, cols: list[str], json_cols: set[str]) -> None:
        """Upserta `rows` en lotes hacia la nube con reintentos y backoff."""
        batch = int(self.cfg["batch_size"])
        max_retries = int(self.cfg["max_retries"])
        base = float(self.cfg["backoff_base_seconds"])
        n = len(rows)
        if n == 0:
            return
        self._log(f"  {table}: {n} fila(s) → nube (lotes de {batch})", "debug")
        for start in range(0, n, batch):
            chunk = [self._jsonify(r, cols, json_cols) for r in rows[start : start + batch]]
            attempt = 0
            while True:
                try:
                    with cloud.cursor() as cur:
                        cur.executemany(upsert, chunk)
                    cloud.commit()
                    self.stats[table]["updates"] += len(chunk)
                    break
                except Exception as e:  # noqa: BLE001
                    cloud.rollback()
                    attempt += 1
                    if attempt > max_retries:
                        raise RuntimeError(
                            f"lote {start // batch + 1} falló tras {max_retries} reintentos: {e}"
                        ) from e
                    sleep_s = base ** attempt + random.uniform(0, 1)
                    self._log(
                        f"  {table}: lote {start // batch + 1} error ({e}); "
                        f"reintento {attempt}/{max_retries} en {sleep_s:.0f}s",
                        "warn",
                    )
                    time.sleep(sleep_s)

    # ── Extras ────────────────────────────────────────────────────────────

    def _log_sizes(self, local, cloud, result: dict[str, Any]) -> None:
        try:
            for name, conn in (("local", local), ("cloud", cloud)):
                with conn.cursor() as cur:
                    cur.execute(
                        "select pg_size_pretty(pg_database_size(current_database()))"
                    )
                    size = cur.fetchone()[0]
                    result["db_sizes"][name] = size
                    self._log(f"  DB {name}: {size}", "info")
        except Exception as e:  # noqa: BLE001
            self._log(f"  no se pudo medir tamaño de DB: {e}", "debug")

    def _append_run(self, result: dict[str, Any]) -> None:
        logs_dir().mkdir(exist_ok=True)
        line = json.dumps(result, ensure_ascii=False, default=str)
        with open(RUNS_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
