"""Widgets reutilizables (estilo Uber: blanco/negro, trazos finos, sin sombras)."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from meshweave.ui import icons
from meshweave.ui.theme import FONT_HEAD, FONT_MONO, FONT_UI, C


def card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8, **kw)


def h2(parent, text: str, color: str = "text") -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text,
                        font=ctk.CTkFont(*FONT_HEAD), text_color=C[color])


def mono_box(parent) -> ctk.CTkTextbox:
    return ctk.CTkTextbox(
        parent, fg_color="#ffffff", border_color=C["border"], border_width=1,
        corner_radius=8, text_color=C["text"],
        font=ctk.CTkFont(*FONT_MONO), wrap="word",
    )


# Estilos de botón: (fondo, hover, texto, borde, radio)
_BTN_STYLES = {
    "ok":     ("#000000", "#333333", "#ffffff", None, 8),        # CTA negro
    "dark":   ("#000000", "#333333", "#ffffff", None, 8),
    "info":   ("#ffffff", "#e5e7eb", "#000000", "#000000", 8),   # contorno negro
    "border": ("#ffffff", "#e5e7eb", "#000000", C["border"], 8),   # contorno accesible
    "err":    ("#d93025", "#b3261e", "#ffffff", None, 8),        # destructivo
    "pill":   ("#ffffff", "#f6f6f6", "#000000", None, 9999),     # píldora (nav negra)
}


def btn(parent, text: str = "", cmd: Callable | None = None, color: str = "border",
        icon: str | None = None, icon_color: str | None = None, **kw) -> ctk.CTkButton:
    """Botón con estilos Uber. `icon` = nombre del icono (opcional)."""
    fg, hv, txt, brd, radius = _BTN_STYLES.get(color, _BTN_STYLES["border"])
    if icon_color is None:
        icon_color = "white" if txt == "#ffffff" else "black"
    kwargs: dict = dict(
        text=text, command=cmd,
        fg_color=fg, hover_color=hv, text_color=txt,
        corner_radius=radius, font=ctk.CTkFont(*FONT_UI),
    )
    if brd:
        kwargs["border_width"] = 1
        kwargs["border_color"] = brd
    if icon:
        kwargs["image"] = icons.photo(icon, 16, icon_color)
        kwargs["compound"] = "left"
    kwargs.update(kw)
    return ctk.CTkButton(parent, **kwargs)


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
