"""Repositorio de configuración de Meshweave.

- `config.json` en %ProgramData%\\Meshweave\\config\\: solo valores públicos
  (hosts, puertos, horarios, tamaños de lote…). NUNCA contraseñas.
- Secretos aparte, en el almacén DPAPI (meshweave.secrets).
- Escritura atómica: temp → validar → os.replace + respaldo .bak.
- Migración única desde la instalación legacy (TunnelCloudFlare) para que el
  sync nocturno continúe sin perder watermarks ni historial.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from meshweave.errors import ConfigError
from meshweave.paths import (
    backups_dir,
    config_dir,
    ensure_dirs,
    logs_dir,
    state_dir,
)
from meshweave.secrets import SecretStore

CONFIG_PATH = config_dir() / "config.json"
STATE_PATH = state_dir() / "sync_state.json"
RUNS_LOG = logs_dir() / "sync_runs.jsonl"
BACKUP_RUNS_LOG = logs_dir() / "backup_runs.jsonl"
BACKUPS_DIR = backups_dir()

DEFAULT_FULL_SYNC_TABLES = [
    "ingest_jobs",
    "ingested_jobs",
    "group_health",
    "alembic_version",
    "alembic_version_ingest",
]

# Claves públicas por defecto (sin secretos).
DEFAULTS: dict[str, Any] = {
    # Túnel
    "tunnel_hostname": "jobs.tonyml.com",
    "tunnel_local_port": 8000,
    "tunnel_id": "",
    "account_tag": "",
    "tunnel_log_level": "info",
    # Backend
    "backend_project_dir": "",
    "backend_command": "",
    "backend_env_file": "",
    "backend_health_url": "http://127.0.0.1:8000/health",
    # Base de datos local (Docker self-hosted)
    "supabase_env": r"E:\Supabase\supabase-project\.env",
    # Base de datos nube — componentes públicos; el password va a DPAPI.
    "cloud_db_host": "",
    "cloud_db_port": 5432,
    "cloud_db_name": "postgres",
    "cloud_db_user": "",
    # Sync engine
    "batch_size": 200,
    "batch_delay_seconds": 1.5,
    "jitter_seconds": 1.0,
    "max_retries": 4,
    "backoff_base_seconds": 2,
    "connect_timeout_seconds": 20,
    "full_sync_tables": list(DEFAULT_FULL_SYNC_TABLES),
    "exclude_tables": [],
    "auto_full_sync_max_rows": 5000,
    # Horarios / tareas de Windows
    "schedule_time": "01:00",
    "schedule_task_name": "MeshweaveSyncService",
    "backup_time": "01:30",
    "backup_task_name": "MeshweaveBackupService",
    "backup_retention_days": 7,
    "backup_container": "supabase-db",
    # Alertas por email (Resend) — claves vacías = se leen del .env del backend
    "alert_on_error": True,
    "alert_on_partial": True,
    "alert_min_interval_minutes": 60,
    "summary_email": True,
    "summary_min_interval_hours": 12,
    "resend_api_key": "",
    "resend_from_email": "",
    "alerts_to_email": "",
    # Actualizaciones
    "check_updates_on_startup": True,
    "update_repo": "meshweave-app",
    # Logging
    "log_level": "INFO",
    "log_max_bytes": 10 * 1024 * 1024,
    "log_backup_count": 5,
}

# ── Config pública ───────────────────────────────────────────────────────────


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in data.items() if v is not None})
        except (OSError, json.JSONDecodeError) as e:
            raise ConfigError(f"No se pudo leer {path.name}: {e}") from e
    return cfg


def save_config(cfg: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    """Escritura atómica con respaldo: temp → validar → os.replace → .bak."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cfg, indent=2, ensure_ascii=False)
    # Validar que lo que escribimos se puede releer (no corromper el archivo).
    json.loads(payload)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    try:
        shutil.copy2(path, path.with_suffix(".bak"))
    except OSError:
        pass


def read_env_file(env_path: Path) -> dict[str, str]:
    """Lee KEY=VALUE de un .env (ignora comentarios y \\r)."""
    out: dict[str, str] = {}
    if not env_path.exists():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip("\r")
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


# ── URL de la nube (password desde DPAPI, nunca en config.json) ─────────────


def cloud_db_url(cfg: dict[str, Any] | None = None) -> str:
    """Arma la URL del pooler de la nube. El password sale de DPAPI."""
    cfg = cfg or load_config()
    host = cfg.get("cloud_db_host", "")
    user = cfg.get("cloud_db_user", "")
    if not host or not user:
        raise ConfigError(
            "Faltan los datos de la nube (cloud_db_host / cloud_db_user). "
            "Configúralos en la pestaña Configuración o edita config.json."
        )
    password = SecretStore().get("cloud_db_password")
    if not password:
        raise ConfigError(
            "No hay contraseña de la nube en el almacén seguro (DPAPI). "
            "Configúrala en la pestaña Configuración."
        )
    port = cfg.get("cloud_db_port", 5432)
    db = cfg.get("cloud_db_name", "postgres")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# ── Estado (watermarks + último run) ────────────────────────────────────────


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"watermarks": {}, "last_run": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"watermarks": {}, "last_run": None}


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ── Migración única desde TunnelCloudFlare (legacy) ─────────────────────────
# La carpeta legacy conserva sync_config.json (con la URL completa de la nube),
# sync_state.json (watermarks) y el historial. Copiamos lo que aporta y el
# password va a DPAPI. Se ejecuta una sola vez (marcador en config dir).

_LEGACY_DIR = Path(r"E:\Dev\Herramientas\TunnelCloudFlare")
_MIGRATION_MARKER = config_dir() / ".migrated_from_legacy"


def migrate_legacy(legacy_dir: Path = _LEGACY_DIR) -> bool:
    """Importa config/estado/historial desde la instalación legacy. Idempotente."""
    ensure_dirs()
    if _MIGRATION_MARKER.exists():
        return False
    src_cfg = legacy_dir / "sync_config.json"
    if not src_cfg.exists():
        return False
    try:
        data = json.loads(src_cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    cfg = load_config()
    # URL de la nube → componentes + password a DPAPI (una sola vez).
    url = data.get("cloud_db_url") or ""
    parsed = urlparse(url)
    if parsed.username and parsed.password:
        SecretStore().set("cloud_db_password", parsed.password)
        cfg["cloud_db_host"] = parsed.hostname or cfg["cloud_db_host"]
        cfg["cloud_db_port"] = parsed.port or cfg["cloud_db_port"]
        cfg["cloud_db_name"] = (parsed.path.lstrip("/") or cfg["cloud_db_name"])
        cfg["cloud_db_user"] = parsed.username
    # El resto de claves públicas que existan en el legacy.
    for key in (
        "supabase_env", "batch_size", "batch_delay_seconds", "jitter_seconds",
        "max_retries", "backoff_base_seconds", "connect_timeout_seconds",
        "schedule_time", "backup_time", "backup_retention_days", "backup_container",
        "alert_on_error", "alert_on_partial", "alert_min_interval_minutes",
        "summary_email", "summary_min_interval_hours", "full_sync_tables",
        "exclude_tables",
    ):
        if key in data and data[key] is not None:
            cfg[key] = data[key]
    # Tareas: nuevos nombres Meshweave (no heredar los viejos nombres).
    # Ruta del backend desde backend.config.json legacy.
    legacy_backend = legacy_dir / "backend.config.json"
    try:
        bdata = json.loads(legacy_backend.read_text(encoding="utf-8"))
        if bdata.get("project_dir"):
            cfg["backend_project_dir"] = bdata["project_dir"]
    except (OSError, json.JSONDecodeError):
        pass
    # Credenciales del túnel: TunnelSecret → DPAPI; AccountTag/TunnelID → config.
    legacy_creds = legacy_dir / "credentials.json"
    try:
        cdata = json.loads(legacy_creds.read_text(encoding="utf-8"))
        if cdata.get("TunnelSecret"):
            SecretStore().set("tunnel_secret", cdata["TunnelSecret"])
        if cdata.get("AccountTag"):
            cfg["account_tag"] = cdata["AccountTag"]
        if cdata.get("TunnelID") and not cfg.get("tunnel_id"):
            cfg["tunnel_id"] = cdata["TunnelID"]
    except (OSError, json.JSONDecodeError):
        pass
    save_config(cfg)

    # Estado (watermarks) e historial → carpetas nuevas.
    for name, dest in (
        ("sync_state.json", STATE_PATH),
        ("sync_runs.jsonl", RUNS_LOG),
        ("backup_runs.jsonl", BACKUP_RUNS_LOG),
    ):
        src = legacy_dir / name
        if src.exists():
            try:
                shutil.copy2(src, dest)
            except OSError:
                pass
    # Últimos dumps (solo los recientes, sin pasarse de la retención).
    try:
        retention = int(cfg.get("backup_retention_days", 7))
        import time
        cutoff = time.time() - retention * 86400
        for f in sorted((legacy_dir / "backups").glob("cloud-*.dump"))[-retention:]:
            if f.stat().st_mtime >= cutoff:
                shutil.copy2(f, BACKUPS_DIR / f.name)
    except OSError:
        pass

    _MIGRATION_MARKER.parent.mkdir(parents=True, exist_ok=True)
    _MIGRATION_MARKER.write_text("1", encoding="utf-8")
    return True
