"""Resolución de rutas del sistema (estándar Windows, sin rutas absolutas).

- Datos del sistema (config, logs, state, backups, bin):  %ProgramData%\\Meshweave
- Datos del usuario (cache, downloads, updates):          %LOCALAPPDATA%\\Meshweave
- Código/ejecutable: carpeta del repo (dev) o del .exe (frozen).

En desarrollo se puede redirigir todo con la variable de entorno
MESHWEAVE_DATA_DIR (también la usa el test suite para no tocar ProgramData).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Meshweave"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Raíz del código: repo (dev) o carpeta del ejecutable (frozen)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """%ProgramData%\\Meshweave — datos del sistema (config, logs, estado…)."""
    override = os.environ.get("MESHWEAVE_DATA_DIR")
    if override:
        return Path(override)
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    return Path(program_data) / APP_NAME


def user_data_dir() -> Path:
    """%LOCALAPPDATA%\\Meshweave — datos específicos del usuario (cache, updates)."""
    override = os.environ.get("MESHWEAVE_USER_DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    return Path(local) / APP_NAME


def config_dir() -> Path:
    return data_dir() / "config"


def logs_dir() -> Path:
    return data_dir() / "logs"


def state_dir() -> Path:
    return data_dir() / "state"


def backups_dir() -> Path:
    return data_dir() / "backups"


def bin_dir() -> Path:
    """Binarios descargados (cloudflared.exe)."""
    return data_dir() / "bin"


def runtime_dir() -> Path:
    """Artefactos generados en runtime (config.runtime.yml, credentials.json)."""
    return data_dir() / "runtime"


def cache_dir() -> Path:
    return user_data_dir() / "cache"


def downloads_dir() -> Path:
    return user_data_dir() / "downloads"


def updates_dir() -> Path:
    return user_data_dir() / "updates"


def secrets_path() -> Path:
    return data_dir() / "secrets.bin"


def ensure_dirs() -> None:
    """Crea todos los directorios de datos si no existen (ProgramData es
    escribible por usuarios estándar para subcarpetas nuevas)."""
    for d in (
        data_dir(), user_data_dir(), config_dir(), logs_dir(), state_dir(),
        backups_dir(), bin_dir(), runtime_dir(), cache_dir(),
        downloads_dir(), updates_dir(),
    ):
        d.mkdir(parents=True, exist_ok=True)
