"""Actualizaciones de Meshweave (Etapa 8).

Por ahora la vía más estable: consultar la última release de GitHub, informar
si hay actualización, descargar el instalador y abrir la página de Releases.
La app NO se reemplaza a sí misma en caliente (riesgo de corrupción).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from meshweave import GITHUB_REPO, __version__
from meshweave.paths import downloads_dir


def _api_url(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/releases/latest"


def latest_release(repo: str = GITHUB_REPO) -> dict[str, Any]:
    req = urllib.request.Request(_api_url(repo), headers={
        "User-Agent": "meshweave/1.0", "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"tag_name": "", "body": "", "assets": [], "html_url": ""}
        raise


def check_update(repo: str = GITHUB_REPO) -> dict[str, Any]:
    """Devuelve info de actualización o {"update": False} si no hay."""
    try:
        rel = latest_release(repo)
    except Exception as e:  # noqa: BLE001
        return {"update": False, "error": str(e)}
    tag = (rel.get("tag_name") or "").lstrip("v")
    if not tag:
        return {"update": False, "error": "No hay releases publicadas todavía."}
    current = __version__.lstrip("v")
    try:
        def _num(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.split(".")[:3])
        update = _num(tag) > _num(current)
    except ValueError:
        update = tag != current
    assets = rel.get("assets") or []
    return {
        "update": update,
        "current": current,
        "latest": tag,
        "notes": rel.get("body") or "",
        "html_url": rel.get("html_url") or f"https://github.com/{repo}/releases",
        "assets": [
            {"name": a.get("name"), "url": a.get("browser_download_url"), "size": a.get("size")}
            for a in assets
        ],
    }


def download_asset(url: str, filename: str, on_progress=None) -> Path | None:
    """Descarga un asset (instalador) a %LOCALAPPDATA%\\Meshweave\\downloads."""
    downloads_dir().mkdir(parents=True, exist_ok=True)
    target = downloads_dir() / filename
    req = urllib.request.Request(url, headers={"User-Agent": "meshweave/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(target, "wb") as out:
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
        return target
    except Exception:  # noqa: BLE001
        target.unlink(missing_ok=True)
        return None


def open_releases_page(repo: str = GITHUB_REPO) -> None:
    os.startfile(f"https://github.com/{repo}/releases")
