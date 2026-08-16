"""Pestaña Logs: log rotativo de Meshweave en vivo."""
from __future__ import annotations

import customtkinter as ctk

from meshweave.paths import logs_dir
from meshweave.ui.theme import FONT_UI
from meshweave.ui.widgets import btn, card, h2, mono_box, tag_configure


class LogsView:
    def __init__(self, parent, app):
        self.app = app
        self._pos = 0
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = card(parent)
        toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))
        h2(toolbar, "Logs en Vivo").pack(side="left", padx=14, pady=8)
        self.autoscroll = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(toolbar, text="Auto-scroll", variable=self.autoscroll,
                        font=ctk.CTkFont(*FONT_UI)).pack(side="left", padx=10)
        btn(toolbar, "📂 Carpeta logs",
            lambda: __import__("os").startfile(logs_dir()) if logs_dir().exists() else None,
            "border", width=120, height=28).pack(side="right", padx=8, pady=8)
        btn(toolbar, "🔄 Recargar", self.refresh, "border", width=90, height=28).pack(side="right", padx=4, pady=8)

        log_card = card(parent)
        log_card.grid(row=1, column=0, sticky="nsew", padx=6, pady=(3, 6))
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(0, weight=1)
        self.box = mono_box(log_card)
        self.box.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.box.configure(state="disabled")
        tag_configure(self.box)
        self.refresh()

    def refresh(self):
        path = logs_dir() / "meshweave.log"
        if not path.exists():
            self.box.configure(state="normal")
            self.box.delete("1.0", "end")
            self.box.insert("1.0", "(meshweave.log todavía no existe)")
            self.box.configure(state="disabled")
            return
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        if len(lines) > self._pos:
            new = lines[self._pos:]
            self.box.configure(state="normal")
            tb = getattr(self.box, "_textbox", None)
            for ln in new[-400:]:
                level = "info"
                low = ln.lower()
                if "error" in low or "crit" in low:
                    level = "err"
                elif "warn" in low:
                    level = "warn"
                tag = {"err": "err", "warn": "warn"}.get(level, "info")
                if tb is not None:
                    tb.insert("end", ln + "\n", tag)
                else:
                    self.box.insert("end", ln + "\n")
            if self.autoscroll.get() and tb is not None:
                tb.see("end")
            self.box.configure(state="disabled")
            self._pos = len(lines)
