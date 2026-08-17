"""Meshweave — centro de control local (túnel, backend, sync, backups, alertas)."""

# La versión de un build la escribe scripts/build.ps1 en _build_version.py
# (gitignored). En desarrollo no existe → se usa la versión base.
try:
    from meshweave._build_version import __version__ as _build_version
except ImportError:
    _build_version = "0.1.0"

__version__ = _build_version

APP_NAME = "Meshweave"
APP_ID = "com.meshweave.desktop"
GITHUB_REPO = "meshweave-app"
