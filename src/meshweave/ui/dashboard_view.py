"""Panel principal: estado general, controles del túnel, consola."""
from __future__ import annotations

import customtkinter as ctk

from meshweave.config import load_config
from meshweave.ui.theme import FONT_MONO, FONT_UI, C
from meshweave.ui.widgets import append_line, btn, card, h2, mono_box, tag_configure


class DashboardView:
    def __init__(self, parent, app):
        self.app = app
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(2, weight=1)

        # ── Status banner ──
        banner = card(parent)
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 3))

        self._status_dot = ctk.CTkLabel(banner, text="●",
                                        font=ctk.CTkFont("Segoe UI", 40), text_color=C["muted"])
        self._status_dot.pack(side="left", padx=18, pady=14)

        meta = ctk.CTkFrame(banner, fg_color="transparent")
        meta.pack(side="left", pady=10, fill="y")
        self._lbl_status = ctk.CTkLabel(meta, text="INACTIVO",
                                        font=ctk.CTkFont("Segoe UI Black", 24), text_color=C["muted"])
        self._lbl_status.pack(anchor="w")
        self._lbl_uptime = ctk.CTkLabel(meta, text="Uptime: —",
                                        font=ctk.CTkFont(*FONT_UI), text_color=C["sub"])
        self._lbl_uptime.pack(anchor="w")

        right = ctk.CTkFrame(banner, fg_color="transparent")
        right.pack(side="right", padx=16)
        self._lbl_sync = ctk.CTkLabel(right, text="Sync: —", font=ctk.CTkFont(*FONT_UI), text_color=C["muted"])
        self._lbl_sync.pack(anchor="e")
        self._lbl_backend = ctk.CTkLabel(right, text="Backend: —", font=ctk.CTkFont(*FONT_UI), text_color=C["muted"])
        self._lbl_backend.pack(anchor="e")
        self._lbl_tasks = ctk.CTkLabel(right, text="Tareas: —", font=ctk.CTkFont(*FONT_UI), text_color=C["muted"])
        self._lbl_tasks.pack(anchor="e")
        self._lbl_checklist = ctk.CTkLabel(right, text="Estado: —",
                                           font=ctk.CTkFont(*FONT_UI), text_color=C["muted"],
                                           cursor="hand2")
        self._lbl_checklist.pack(anchor="e")
        self._lbl_checklist.bind("<Button-1>", lambda _e: self.app._tabs.set("Estado"))

        # ── Control del túnel ──
        ctrl = card(parent)
        ctrl.grid(row=1, column=0, sticky="ew", padx=(6, 3), pady=3)
        h2(ctrl, "Túnel Cloudflare").pack(anchor="w", padx=14, pady=(12, 6))
        row = ctk.CTkFrame(ctrl, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 12))
        self._btn_start = btn(row, "Iniciar Túnel", self.app.actions.tunnel_start, "ok", icon="play")
        self._btn_stop = btn(row, "Detener", self.app.actions.tunnel_stop, "err", icon="stop", state="disabled")
        self._btn_restart = btn(row, "Reiniciar", self.app.actions.tunnel_restart, "border", icon="refresh", state="disabled")
        for b in (self._btn_start, self._btn_stop, self._btn_restart):
            b.pack(side="left", padx=4, ipady=2)

        # ── Parámetros ──
        pcard = card(parent)
        pcard.grid(row=1, column=1, sticky="nsew", padx=(3, 6), pady=3)
        h2(pcard, "Parámetros").pack(anchor="w", padx=14, pady=(12, 4))
        self._params = {}
        for k in ("Tunnel ID", "Hostname", "Backend", "cloudflared"):
            r = ctk.CTkFrame(pcard, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(r, text=f"{k}:", width=90, font=ctk.CTkFont(*FONT_UI),
                         text_color=C["muted"], anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(r, text="—", font=ctk.CTkFont(*FONT_MONO), text_color=C["text"], anchor="w")
            lbl.pack(side="left")
            self._params[k] = lbl

        # ── Consola ──
        console_card = card(parent)
        console_card.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=(3, 6))
        console_card.columnconfigure(0, weight=1)
        console_card.rowconfigure(1, weight=1)
        head = ctk.CTkFrame(console_card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        h2(console_card, "Output").grid(row=0, column=0, sticky="w", padx=14, pady=(8, 2))
        btn(head, "Limpiar", self.clear, "border", width=70, height=26).pack(side="right")
        self.console = mono_box(console_card)
        self.console.grid(row=1, column=0, sticky="nsew", padx=8, pady=(2, 8))
        self.console.configure(state="disabled")
        tag_configure(self.console)

    def set_checklist(self, errs: int, warns: int):
        """Indicador del checklist en el banner (clic → pestaña Estado)."""
        n = errs + warns
        if n:
            self._lbl_checklist.configure(
                text=f"Estado: {n} pendiente{'s' if n != 1 else ''}",
                text_color=C["err"] if errs else C["warn"])
        else:
            self._lbl_checklist.configure(text="Estado: listo", text_color=C["ok"])

    def clear(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def append(self, line: str, level: str = "info"):
        append_line(self.console, line, level)

    def refresh(self):
        tunnel = self.app.tunnel
        running = tunnel.running
        self._btn_start.configure(state="disabled" if running else "normal")
        self._btn_stop.configure(state="normal" if running else "disabled")
        self._btn_restart.configure(state="normal" if running else "disabled")
        if running:
            self._status_dot.configure(text_color=C["ok"])
            self._lbl_status.configure(text="TÚNEL ACTIVO", text_color=C["ok"])
            self._lbl_uptime.configure(text=f"Uptime: {tunnel.uptime}")
        else:
            self._status_dot.configure(text_color=C["muted"])
            self._lbl_status.configure(text="INACTIVO", text_color=C["muted"])
            self._lbl_uptime.configure(text="Uptime: —")
        try:
            cfg = load_config()
            self._params["Tunnel ID"].configure(text=(cfg.get("tunnel_id") or "—")[:22] + "…")
            self._params["Hostname"].configure(text=cfg.get("tunnel_hostname", "—"))
            self._params["Backend"].configure(text=f"http://127.0.0.1:{cfg.get('tunnel_local_port', 8000)}")
        except Exception:
            pass
        from meshweave.services.cloudflared_manager import installed_version
        self._params["cloudflared"].configure(text=installed_version() or "no instalado")
        self._lbl_backend.configure(
            text=f"Backend: {'activo' if self.app.backend.running else 'detenido'}",
            text_color=C["ok"] if self.app.backend.running else C["muted"])
