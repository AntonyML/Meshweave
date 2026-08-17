"""Genera el icono de Meshweave (assets/meshweave.ico + assets/meshweave.png).

Diseño: cuadrado redondeado con gradiente azul→violeta, patrón de malla
("mesh") sutil y monograma "M" blanco. Requiere Pillow:

    pip install Pillow
    python scripts\\make_icon.py

Regenera los assets con un solo comando; los binarios se versionan en el repo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets"
SIZE = 256
TOP = (37, 99, 235)        # #2563eb (azul)
BOTTOM = (124, 58, 237)    # #7c3aed (violeta)
FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
]


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _load_font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_icon() -> Image.Image:
    # Fondo con gradiente vertical.
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        c = _lerp(TOP, BOTTOM, t)
        for x in range(SIZE):
            px[x, y] = (*c, 255)

    # Máscara de esquinas redondeadas.
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [8, 8, SIZE - 9, SIZE - 9], radius=56, fill=255)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)

    # Patrón de malla: puntos en rejilla (desaparece en tamaños pequeños).
    spacing = 32
    for gx in range(8, SIZE - 8, spacing):
        for gy in range(8, SIZE - 8, spacing):
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=(255, 255, 255, 46))

    # Monograma "M".
    font = _load_font(178)
    d.text((SIZE / 2, SIZE / 2 + 8), "M", font=font,
           fill=(255, 255, 255, 255), anchor="mm")

    # Borde interior sutil.
    d.rounded_rectangle([8, 8, SIZE - 9, SIZE - 9], radius=56,
                        outline=(255, 255, 255, 46), width=6)
    return img


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = build_icon()
    ico = OUT_DIR / "meshweave.ico"
    png = OUT_DIR / "meshweave.png"
    img.save(png)
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                         (64, 64), (128, 128), (256, 256)])
    print(f"Generado: {png} ({png.stat().st_size} bytes)")
    print(f"Generado: {ico} ({ico.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
