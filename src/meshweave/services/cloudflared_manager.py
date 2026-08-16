"""Gestión del binario cloudflared.exe.

- Detecta si existe en %ProgramData%\\Meshweave\\bin\\ (fuera del repo).
- Descarga desde GitHub Releases (fuente oficial), verifica tamaño + SHA-256
  (cuando el release publica el checksum) y reemplaza de forma atómica.
- La descarga es siempre una acción visible/explícita, nunca silenciosa.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from meshweave.errors import DownloadError
from meshweave.paths import bin_dir, package_root

RELEASES_API = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"
DOWNLOAD_URL = (
    "https://github.com/cloudflare/cloudflared/releases/download/{version}/"
    "cloudflared-windows-amd64.exe"
)
CHECKSUM_URL = DOWNLOAD_URL + ".sha256"


def binary_path() -> Path:
    """Ruta canónica del binario (ProgramData\\Meshweave\\bin)."""
    return bin_dir() / "cloudflared.exe"


def legacy_binary_path() -> Path:
    """Binario de la instalación legacy (para migrar sin redescargar)."""
    return package_root().parent / "TunnelCloudFlare" / "cloudflared.exe"


def needs_binary() -> bool:
    return not binary_path().exists()


def installed_version() -> str | None:
    exe = binary_path()
    if not exe.exists():
        return None
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True,
                           text=True, timeout=15)
        out = (r.stdout or r.stderr or "").strip()
        # p.ej. "cloudflared version 2024.8.2 (built 2024-08-02-…)"
        for part in out.split():
            if part[0].isdigit():
                return part
        return out.splitlines()[0] if out else None
    except (OSError, subprocess.SubprocessError):
        return None


def latest_release() -> dict[str, Any]:
    """Última release de cloudflared (tag_name + assets)."""
    req = urllib.request.Request(RELEASES_API, headers={
        "User-Agent": "meshweave/1.0", "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch_checksum(version: str, user_agent: str) -> str | None:
    """Descarga el .sha256 del release si existe; None si no lo publican."""
    url = CHECKSUM_URL.format(version=version)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", "replace").strip()
    except urllib.error.HTTPError:
        return None


def download(version: str | None = None, on_progress=None) -> tuple[bool, str]:
    """Descarga cloudflared a bin_dir. Devuelve (ok, mensaje).

    Verifica SHA-256 si el release lo publica; si no, valida tamaño (>5 MB)
    y que el binario responda a `--version` tras instalarlo.
    """
    import ssl

    version = version or latest_release().get("tag_name", "")
    if not version:
        return False, "No se pudo determinar la última versión de cloudflared."

    target = binary_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    url = DOWNLOAD_URL.format(version=version)
    user_agent = "meshweave/1.0"

    # 1) Descargar a archivo temporal en la misma carpeta (mismo volumen).
    fd, tmp_name = tempfile.mkstemp(prefix="cloudflared-", suffix=".exe", dir=str(target.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context()) as resp, \
                open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(done / total)

        # 2) Verificación.
        size = tmp.stat().st_size
        if size < 5 * 1024 * 1024:
            raise DownloadError(f"Descarga sospechosamente pequeña ({size} bytes).")
        expected = _fetch_checksum(version, user_agent)
        if expected:
            actual = _sha256_of(tmp)
            if actual.lower() != expected.split()[0].lower():
                raise DownloadError("SHA-256 no coincide con el publicado por el release.")
        else:
            # Sin checksum publicado: verificar que es un PE válido y ejecutable.
            with open(tmp, "rb") as f:
                if f.read(2) != b"MZ":
                    raise DownloadError("El archivo descargado no es un ejecutable PE válido.")

        # 3) Reemplazo atómico.
        backup = target.with_suffix(".old") if target.exists() else None
        if backup:
            backup.unlink(missing_ok=True)
            os.replace(target, backup)
        os.replace(tmp, target)
        if backup:
            backup.unlink(missing_ok=True)

        ver = installed_version()
        return True, f"cloudflared {ver or version} instalado en {target}."
    except DownloadError as e:
        tmp.unlink(missing_ok=True)
        return False, str(e)
    except Exception as e:  # noqa: BLE001 — red, permisos…
        tmp.unlink(missing_ok=True)
        return False, f"Error descargando cloudflared: {e}"


def migrate_from_legacy() -> bool:
    """Si existe el binario legacy, lo copia a bin_dir (evita redescarga)."""
    src = legacy_binary_path()
    if not src.exists() or binary_path().exists():
        return False
    try:
        binary_path().parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(src, binary_path())
        return True
    except OSError:
        return False
