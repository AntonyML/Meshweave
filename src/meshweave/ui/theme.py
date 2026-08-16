"""Tema visual y fuentes de Meshweave."""
from __future__ import annotations

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = dict(
    ok="#22c55e",
    err="#ef4444",
    warn="#f59e0b",
    info="#38bdf8",
    purple="#a78bfa",
    muted="#64748b",
    card="#1e293b",
    darker="#0f172a",
    text="#e2e8f0",
    sub="#94a3b8",
    border="#334155",
)

FONT_MONO = ("Consolas", 11)
FONT_UI = ("Segoe UI", 12)
FONT_HEAD = ("Segoe UI Semibold", 13)
