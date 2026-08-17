"""Tema visual de Meshweave — estilo Uber (kiosco monocromo).

Blanco y negro: canvas blanco, bandas estructurales negras (cabecera), trazos
finos 1px, radios 8px, sin sombras. El único acento cromático de la UI es el
teal de la pestaña activa; el resto del color es semántico (estado ok/err).
"""
from __future__ import annotations

import customtkinter as ctk

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

C = dict(
    # ── Semánticos (únicos acentos, solo para estado) ──
    ok="#1a7f37",        # éxito (verde apagado, legible sobre blanco)
    err="#d93025",       # error / destructivo
    warn="#9a6700",      # aviso (ámbar oscuro)
    info="#000000",      # acento informativo = tinta
    purple="#4b4b4b",    # acentos secundarios (estados del log)

    # ── Superficies y texto ──
    text="#000000",      # tinta principal (Jet Black)
    sub="#5e5e5e",       # texto secundario (Slate)
    muted="#767676",     # helper / bordes de input (Iron Gray)
    card="#f6f6f6",      # superficie de tarjetas (Mist Gray)
    darker="#000000",    # banda estructural: cabecera/footer (Jet Black)
    border="#767676",    # trazo fino (hairline)
    accent="#9dcdd6",    # teal: pestaña activa (único acento de la UI)

    # ── Texto sobre bandas negras ──
    ondark="#ffffff",
    ondark_sub="#afafaf",
)

FONT_MONO = ("Consolas", 11)
FONT_UI = ("Segoe UI", 12)
FONT_HEAD = ("Segoe UI Semibold", 13)
