"""Genera los iconos de la UI desde fuentes SVG → PNG (assets/icons/*.png).

Los SVG (24x24, estilo Lucide/Material, monocromo) son la fuente de verdad.
Este script los rasteriza con svglib + reportlab a 64px, los baja a 32px
(AA suave) y genera variantes de color y tamaño:

    assets/icons/<nombre>-<color>-<tamaño>.png

Colores: black, white y variantes de estado (ok/warn/err) donde aplican.
Requiere (solo para regenerar): pip install svglib reportlab rlPyCairo Pillow

El runtime NO necesita PIL: la UI carga los PNG con tkinter.PhotoImage.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icons"

# ── Fuentes SVG (viewBox 24x24) ───────────────────────────────────────────
_STROKE = ('fill="none" stroke="black" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round"')

ICONS: dict[str, str] = {
    "check": '<path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z" fill="black"/>',
    "error": ('<path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 '
              '9.2 12 2.9 5.7 4.3 4.3 10.6 10.6 16.9 4.3z" fill="black"/>'),
    "warn": ('<path d="M12 2 1 21h22L12 2z" fill="black"/>'
             '<rect x="11.1" y="8.8" width="1.8" height="6.6" rx="0.9" fill="black"/>'
             '<circle cx="12" cy="18.2" r="1.3" fill="black"/>'),
    "info": (f'<circle cx="12" cy="12" r="10" {_STROKE}/>'
             f'<path d="M12 16v-4" {_STROKE}/>'
             '<circle cx="12" cy="8" r="1.6" fill="black"/>'),
    "play": '<path d="M8 5v14l11-7z" fill="black"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="black"/>',
    "refresh": (f'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" {_STROKE}/>'
                f'<path d="M21 3v5h-5" {_STROKE}/>'
                f'<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" {_STROKE}/>'
                f'<path d="M8 16H3v5" {_STROKE}/>'),
    "flask": (f'<path d="M10 2v6.5a2 2 0 0 1-.2.9L4.7 20.1a1 1 0 0 0 .9 1.4h12.8a1 1 0 0 0 '
              f'.9-1.4l-5.1-10.7a2 2 0 0 1-.2-.9V2" {_STROKE}/>'
              f'<path d="M8.5 2h7" {_STROKE}/>'
              f'<path d="M7 16h10" {_STROKE}/>'),
    "save": (f'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" {_STROKE}/>'
             f'<path d="M17 21v-8H7v8" {_STROKE}/>'
             f'<path d="M7 3v5h8" {_STROKE}/>'),
    "search": (f'<circle cx="11" cy="11" r="7" {_STROKE}/>'
               f'<path d="M21 21l-4.3-4.3" {_STROKE}/>'),
    "folder": (f'<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.6 '
               f'3.9A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z" {_STROKE}/>'),
    "restore": (f'<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" {_STROKE}/>'
                f'<path d="M3 3v5h5" {_STROKE}/>'),
    "calendar": (f'<rect x="3" y="4" width="18" height="17" rx="2" {_STROKE}/>'
                 f'<path d="M16 2v4M8 2v4M3 10h18" {_STROKE}/>'),
    "trash": (f'<path d="M3 6h18" {_STROKE}/>'
              f'<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 '
              f'0 1 2 2v2" {_STROKE}/>'
              f'<path d="M10 11v6M14 11v6" {_STROKE}/>'),
    "mail": (f'<rect x="2" y="4" width="20" height="16" rx="2" {_STROKE}/>'
             f'<path d="m22 7-10 6L2 7" {_STROKE}/>'),
    "upload": (f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" {_STROKE}/>'
               f'<path d="m17 8-5-5-5 5" {_STROKE}/>'
               f'<path d="M12 3v12" {_STROKE}/>'),
    "download": (f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" {_STROKE}/>'
                 f'<path d="m7 10 5 5 5-5" {_STROKE}/>'
                 f'<path d="M12 15V3" {_STROKE}/>'),
    "clock": (f'<circle cx="12" cy="12" r="10" {_STROKE}/>'
              f'<path d="M12 6v6l4 2" {_STROKE}/>'),
    "eye": (f'<path d="M1.5 12S4.5 5 12 5s10.5 7 10.5 7-3 7-10.5 7S1.5 12 1.5 12z" {_STROKE}/>'
            f'<circle cx="12" cy="12" r="3" {_STROKE}/>'),
    "eye-off": (f'<path d="M1.5 12S4.5 5 12 5s10.5 7 10.5 7-3 7-10.5 7S1.5 12 1.5 12z" {_STROKE}/>'
                f'<circle cx="12" cy="12" r="3" {_STROKE}/>'
                f'<path d="M3.5 20.5 20.5 3.5" {_STROKE}/>'),
}

# ── Colores y tamaños ──────────────────────────────────────────────────────
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
OK = (26, 127, 55)        # #1a7f37
WARN = (154, 103, 0)      # #9a6700
ERR = (217, 48, 37)       # #d93025

# Variantes de color por icono: negro (default) + blanco + estados.
COLORS: dict[str, list[str]] = {
    "check": ["black", "white", "ok", "warn", "err"],
    "warn": ["black", "white", "warn"],
    "error": ["black", "white", "err"],
}
_PALETTE = {"black": BLACK, "white": WHITE, "ok": OK, "warn": WARN, "err": ERR}

SIZES = (14, 16, 18, 20, 24)


def render_black(svg: str, size: int = 32) -> Image.Image:
    """Rasteriza el SVG a `size`px con alpha (negro sobre transparente)."""
    tmp = ROOT / "build" / "icons_tmp.svg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    # Los dicts guardan solo el contenido: envuelve en un SVG 24x24 a 32px.
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" '
           'viewBox="0 0 24 24">' + svg + "</svg>")
    tmp.write_text(svg, encoding="utf-8")
    drawing = svg2rlg(str(tmp))
    big = ROOT / "build" / "icons_tmp.png"
    # dpi=192 → 64px sobre un viewBox de 32 → downscale para AA suave.
    renderPM.drawToFile(drawing, str(big), fmt="PNG", dpi=192)
    img = Image.open(big).convert("RGBA").resize((size, size), Image.LANCZOS)
    gray = img.convert("L")
    alpha = ImageOps.invert(gray)
    # Limpia el granulado fantasma de la rasterización (alpha < 8 → 0).
    alpha = alpha.point(lambda v: 0 if v < 8 else v)
    out = Image.new("RGBA", (size, size), (*BLACK, 255))
    out.putalpha(alpha)
    return out


def colorize(img: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Recolorea el glifo preservando el antialias (alpha intacto)."""
    alpha = img.split()[3]
    out = Image.new("RGBA", img.size, (*color, 255))
    out.putalpha(alpha)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, svg in sorted(ICONS.items()):
        base = render_black(svg)
        for color in COLORS.get(name, ["black", "white"]):
            src = base if color == "black" else colorize(base, _PALETTE[color])
            for size in SIZES:
                src.resize((size, size), Image.LANCZOS).save(
                    OUT / f"{name}-{color}-{size}.png")
                total += 1

    # Marca de la app (con color propio): escala el icono principal.
    brand = ROOT / "assets" / "meshweave.png"
    if brand.exists():
        src = Image.open(brand).convert("RGBA")
        for size in SIZES:
            src.resize((size, size), Image.LANCZOS).save(OUT / f"brand-{size}.png")
            total += 1

    print(f"Generados {total} PNG en {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
