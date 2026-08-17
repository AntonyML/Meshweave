"""Carga de iconos de la UI.

Los iconos son PNG vectoriales pre-renderizados (fuentes SVG en
scripts/make_icons.py → assets/icons/*.png). Se cargan con
``tkinter.PhotoImage`` (PNG nativo de Tk 8.6) — sin dependencia de PIL en
runtime. Las imágenes se cachean para no recargarlas.

Uso:
    icons.photo("play", 16)                  # negro (default)
    icons.photo("check", 14, "ok")           # variante de color
    icons.photo("brand", 20)                 # logo de la app (a color)
"""
from __future__ import annotations

import warnings
from tkinter import PhotoImage

from meshweave.paths import assets_dir

# Usamos PhotoImage a propósito (iconos pre-renderizados a tamaño fijo, sin
# PIL en runtime). customtkinter avisa de que no escala en HighDPI; lo
# silenciamos porque cada PNG ya viene al tamaño exacto de pantalla.
warnings.filterwarnings("ignore", message=r"Given image is not CTkImage.*")

_cache: dict[tuple[str, int, str], PhotoImage] = {}


def photo(name: str, size: int = 16, color: str = "black") -> PhotoImage:
    """Devuelve el icono como PhotoImage (cacheado). Guarda la referencia
    en la caché para que Tk no la recolecte."""
    key = (name, size, color)
    img = _cache.get(key)
    if img is None:
        if name == "brand":
            path = assets_dir() / "icons" / f"brand-{size}.png"
        else:
            path = assets_dir() / "icons" / f"{name}-{color}-{size}.png"
        img = PhotoImage(file=str(path))
        _cache[key] = img
    return img
