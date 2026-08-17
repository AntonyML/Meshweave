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
from meshweave.ui.widgets import btn, card, h2, status_pill

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
        self.output = ctk.CTkScrollableFrame(out, fg_color="transparent")
        self.output.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.output.columnconfigure(0, weight=1)

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

        for child in self.output.winfo_children():
            child.destroy()
        for row, i in enumerate(items):
            item = card(self.output)
            item.grid(row=row, column=0, sticky="ew", padx=2, pady=4)
            item.columnconfigure(1, weight=1)
            icon_name, icon_color = _ICONS.get(i.status, ("info", "black"))
            ctk.CTkLabel(item, image=icons.photo(icon_name, 20, icon_color), text="", width=28).grid(
                row=0, column=0, rowspan=2, padx=(12, 6), pady=12, sticky="n")
            ctk.CTkLabel(item, text=i.label, text_color=C["text"], anchor="w",
                         font=ctk.CTkFont("Segoe UI Semibold", 13)).grid(
                row=0, column=1, sticky="ew", padx=4, pady=(10, 0))
            status_pill(item, i.status.upper(), i.status).grid(row=0, column=2, padx=12, pady=(10, 0), sticky="e")
            ctk.CTkLabel(item, text=f"{i.detail}\n{i.action or ''}", text_color=C["sub"],
                         justify="left", anchor="w", wraplength=700).grid(
                row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=(2, 10))
