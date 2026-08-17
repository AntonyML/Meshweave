"""Pestaña Backend: ruta, arranque/parada controlados y salud de servicios."""
from __future__ import annotations

import threading
from tkinter import filedialog
from urllib.error import HTTPError
from urllib.request import urlopen

import customtkinter as ctk

from meshweave.config import load_config
from meshweave.services.backend_service import default_backend_dir
from meshweave.ui.theme import FONT_MONO, FONT_UI, C
from meshweave.ui.widgets import append_line, btn, card, h2, mono_box, tag_configure


def ping_url(url: str, timeout: int = 3) -> bool:
    try:
        with urlopen(url, timeout=timeout):
            return True
    except HTTPError:
        return True
    except Exception:  # noqa: BLE001
        return False


class BackendView:
    def __init__(self, parent, app):
        self.app = app
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        top = card(parent)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))
        h2(top, "Proyecto FastAPI").pack(anchor="w", padx=14, pady=(12, 4))
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=4)
        self.path_entry = ctk.CTkEntry(row, font=ctk.CTkFont(*FONT_MONO))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=4)
        btn(row, "Buscar carpeta", self._browse, "border").pack(side="left", padx=4)
        btn(row, "Conectar", self._connect, "info").pack(side="left", padx=4)
        self.command_entry = ctk.CTkEntry(top, placeholder_text="Comando (vacío = uvicorn)")
        self.command_entry.pack(fill="x", padx=14, pady=(2, 2))
        self.env_entry = ctk.CTkEntry(top, placeholder_text="Archivo .env (vacío = proyecto/.env)")
        self.env_entry.pack(fill="x", padx=14, pady=(2, 4))
        self.msg_lbl = ctk.CTkLabel(top, text="", text_color=C["sub"], anchor="w")
        self.msg_lbl.pack(fill="x", padx=14, pady=(0, 8))

        controls = card(parent)
        controls.grid(row=1, column=0, sticky="ew", padx=6, pady=3)
        h2(controls, "Control del backend").pack(anchor="w", padx=14, pady=(10, 4))
        self.status_lbl = ctk.CTkLabel(controls, text="● Detenido", text_color=C["muted"],
                                       font=ctk.CTkFont(*FONT_UI))
        self.status_lbl.pack(side="left", padx=14, pady=10)
        self.uptime_lbl = ctk.CTkLabel(controls, text="Uptime: —", text_color=C["sub"])
        self.uptime_lbl.pack(side="left")
        self.btn_start = btn(controls, "Iniciar", self.app.actions.backend_start, "ok", icon="play")
        self.btn_stop = btn(controls, "Detener", self.app.actions.backend_stop, "err", icon="stop", state="disabled")
        self.btn_start.pack(side="right", padx=4, pady=8)
        self.btn_stop.pack(side="right", padx=4, pady=8)

        health = card(parent)
        health.grid(row=2, column=0, sticky="ew", padx=6, pady=3)
        h2(health, "Salud de servicios").pack(anchor="w", padx=14, pady=(10, 2))
        hrow = ctk.CTkFrame(health, fg_color="transparent")
        hrow.pack(fill="x", padx=10, pady=(4, 10))
        self.dot_api = ctk.CTkLabel(hrow, text="● API principal  —", text_color=C["muted"])
        self.dot_api.pack(side="left", padx=8)
        self.dot_ingest = ctk.CTkLabel(hrow, text="● API ingesta (puerto 8001)  —", text_color=C["muted"])
        self.dot_ingest.pack(side="left", padx=8)
        btn(hrow, "Actualizar", self._check_health, "border", icon="refresh").pack(side="right", padx=4)

        out_card = card(parent)
        out_card.grid(row=3, column=0, sticky="nsew", padx=6, pady=(3, 6))
        out_card.columnconfigure(0, weight=1)
        out_card.rowconfigure(1, weight=1)
        h2(out_card, "Salida del backend").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.output = mono_box(out_card)
        self.output.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.output.configure(state="disabled")
        tag_configure(self.output)

        self.path_entry.insert(0, str(default_backend_dir()))
        cfg = load_config()
        self.command_entry.insert(0, cfg.get("backend_command", ""))
        self.env_entry.insert(0, cfg.get("backend_env_file", ""))

    def _browse(self):
        p = filedialog.askdirectory(title="Carpeta del backend FastAPI")
        if p:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, p)
            self._connect()

    def _connect(self):
        p = self.path_entry.get().strip()
        ok, msg = self.app.actions.backend_connect(p, self.command_entry.get().strip(), self.env_entry.get().strip())
        self.msg_lbl.configure(text=msg, text_color=C["ok"] if ok else C["err"])

    def _check_health(self):
        def _go():
            cfg = load_config()
            api = ping_url(cfg.get("backend_health_url") or f"http://127.0.0.1:{cfg.get('tunnel_local_port', 8000)}")
            ingest = ping_url("http://localhost:8001")
            self.app.post(lambda: self._apply_health(api, ingest))
        threading.Thread(target=_go, daemon=True).start()

    def _apply_health(self, api: bool, ingest: bool):
        self.dot_api.configure(text=f"● API principal  {'OK' if api else 'sin respuesta'}",
                               text_color=C["ok"] if api else C["muted"])
        self.dot_ingest.configure(text=f"● API ingesta (puerto 8001)  {'OK' if ingest else 'sin respuesta'}",
                                  text_color=C["ok"] if ingest else C["muted"])

    def append(self, line: str, level: str = "info"):
        append_line(self.output, line, level)

    def refresh(self):
        backend = self.app.backend
        running = backend.running
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.status_lbl.configure(text=f"● {'Activo' if running else 'Detenido'}",
                                  text_color=C["ok"] if running else C["muted"])
        self.uptime_lbl.configure(text=f"Uptime: {backend.uptime}")
        self.app.after(2000, self._check_health)
