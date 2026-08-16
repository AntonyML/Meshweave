"""Widgets reutilizables."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from meshweave.ui.theme import C, FONT_HEAD, FONT_MONO, FONT_UI


def card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=10, **kw)


def h2(parent, text: str, color: str = "text") -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text,
                        font=ctk.CTkFont(*FONT_HEAD), text_color=C[color])


def mono_box(parent) -> ctk.CTkTextbox:
    return ctk.CTkTextbox(
        parent, fg_color=C["darker"], text_color=C["text"],
        font=ctk.CTkFont(*FONT_MONO), wrap="word",
    )


def btn(parent, text: str, cmd: Callable, color: str = "border", **kw) -> ctk.CTkButton:
    colors = {
        "ok": (C["ok"], "#16a34a"),
        "err": (C["err"], "#dc2626"),
        "info": ("#1d4ed8", "#1e40af"),
        "dark": (C["border"], C["muted"]),
        "border": (C["border"], "#475569"),
    }
    fg, hv = colors.get(color, (C["border"], C["muted"]))
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg, hover_color=hv,
        font=ctk.CTkFont(*FONT_UI), **kw
    )


def append_line(box: ctk.CTkTextbox, line: str, level: str = "info", autoscroll: bool = True) -> None:
    """Inserta una línea con tag de color en un mono_box (thread-safe vía .after)."""
    box.configure(state="normal")
    tb = getattr(box, "_textbox", None)
    if tb is not None:
        tag = {"debug": "dim", "info": "info", "warn": "warn", "ok": "ok",
               "error": "err", "state": "state"}.get(level, "info")
        from datetime import datetime
        tb.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] ", "ts")
        tb.insert("end", line + "\n", tag)
        if autoscroll:
            tb.see("end")
    box.configure(state="disabled")


def tag_configure(box: ctk.CTkTextbox, colors: dict[str, str] | None = None) -> None:
    """Configura tags de color en el textbox interno de CTk."""
    tb = getattr(box, "_textbox", None)
    if tb is None:
        return
    colors = colors or {
        "ts": C["muted"], "ok": C["ok"], "err": C["err"], "warn": C["warn"],
        "state": C["purple"], "info": C["info"], "dim": C["sub"],
    }
    for tag, color in colors.items():
        tb.tag_configure(tag, foreground=color)
