"""Pestaña Estado: checklist de preparación en lenguaje natural.

Muestra qué está bien y qué falta, con el motivo (físico / configuración /
servicio / permisos / disco) y qué hacer en cada caso. Los detalles técnicos
quedan en los Logs.
"""
from __future__ import annotations

import threading

import customtkinter as ctk

from meshweave.config import load_config
from meshweave.readiness import CheckItem, check_readiness, summary
from meshweave.ui import icons
from meshweave.ui.theme import FONT_UI, C
from meshweave.ui.widgets import btn, card, h2, mono_box, tag_configure

# (icono, color) por estado — se incrustan como imagen en el textbox.
_ICONS = {"ok": ("check", "ok"), "warn": ("warn", "warn"), "err": ("error", "err")}
_TAGS = {"ok": "ok", "warn": "warn", "err": "err"}


class EstadoView:
    def __init__(self, parent, app):
        self.app = app
        self._last_items: list[CheckItem] = []
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = card(parent)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))
        h2(top, "Estado de la instalación").pack(anchor="w", padx=14, pady=(10, 4))
        self.summary_lbl = ctk.CTkLabel(
            top, text="Revisando…",
            font=ctk.CTkFont("Segoe UI Semibold", 15),
            text_color=C["text"], anchor="w", justify="left", wraplength=850)
        self.summary_lbl.pack(fill="x", padx=14, pady=(0, 4))
        brow = ctk.CTkFrame(top, fg_color="transparent")
        brow.pack(fill="x", padx=10, pady=(2, 10))
        btn(brow, "Revisar ahora", self.refresh, "info", icon="refresh").pack(side="left", padx=4)
        ctk.CTkLabel(
            top,
            text="Cada punto indica qué falta y por qué: [físico] = falta un "
                 "programa/archivo en el PC · [config] = datos por completar · "
                 "[servicio] = algo está caído o sin instalar · [permisos] = requiere "
                 "administrador · [disco] = espacio. Los detalles técnicos están en Logs.",
            font=ctk.CTkFont(*FONT_UI), text_color=C["sub"], wraplength=860,
            anchor="w", justify="left").pack(anchor="w", padx=14, pady=(0, 8))

        out = card(parent)
        out.grid(row=1, column=0, sticky="nsew", padx=6, pady=(3, 6))
        out.columnconfigure(0, weight=1)
        out.rowconfigure(1, weight=1)
        h2(out, "Checklist").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.output = mono_box(out)
        self.output.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.output.configure(state="disabled")
        tag_configure(self.output)

    def refresh(self):
        self.summary_lbl.configure(text="Revisando…", text_color=C["text"])

        def _go():
            try:
                items = check_readiness(load_config())
            except Exception as e:  # noqa: BLE001
                items = [CheckItem(
                    "error", "Chequeo", "err", "servicio",
                    f"No se pudo completar la revisión: {e}",
                    "Revisa los Logs y reintenta.")]
            self.app.post(lambda: self.apply_items(items))

        threading.Thread(target=_go, daemon=True).start()

    def apply_items(self, items: list[CheckItem]) -> None:
        """Renderiza los resultados (debe correr en el hilo principal)."""
        self._last_items = items
        errs, warns, oks = summary(items)
        pending = [i for i in items if i.status != "ok"]
        if not pending:
            self.summary_lbl.configure(text="Todo listo — no falta nada por configurar.",
                                       text_color=C["ok"])
        else:
            nombres = ", ".join(i.label for i in pending)
            if errs:
                self.summary_lbl.configure(
                    text=f"Faltan {errs + warns} cosas por revisar "
                         f"({errs} bloqueantes, {warns} recomendadas): {nombres}",
                    text_color=C["err"])
            else:
                self.summary_lbl.configure(
                    text=f"Faltan {warns} cosas por revisar (recomendadas): {nombres}",
                    text_color=C["warn"])

        tb = getattr(self.output, "_textbox", None)
        self.output.configure(state="normal")
        if tb is not None:
            tb.delete("1.0", "end")
            for i in items:
                tag = _TAGS.get(i.status, "info")
                icon_name, icon_color = _ICONS.get(i.status, ("info", "black"))
                tb.image_create("end", image=icons.photo(icon_name, 14, icon_color))
                tb.insert("end", " " + i.label + "  ", tag)
                tb.insert("end", f"[{i.kind}]\n", "dim")
                tb.insert("end", f"    {i.detail}\n", "info")
                if i.action:
                    tb.insert("end", f"    → {i.action}\n", "state")
        self.output.configure(state="disabled")
