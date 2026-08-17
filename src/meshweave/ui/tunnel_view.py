"""Pestaña Túnel: estado, binario cloudflared, servicio de Windows, config runtime."""
from __future__ import annotations

import customtkinter as ctk

from meshweave.config import load_config
from meshweave.services import cloudflared_manager
from meshweave.services.tunnel_service import cloudflared_service_status, prepare_runtime
from meshweave.ui.theme import FONT_UI, C
from meshweave.ui.widgets import btn, card, h2, mono_box, tag_configure


class TunnelView:
    def __init__(self, parent, app):
        self.app = app
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        top = card(parent)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))
        h2(top, "Túnel Cloudflare").pack(anchor="w", padx=14, pady=(10, 4))

        srow = ctk.CTkFrame(top, fg_color="transparent")
        srow.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(srow, text="Estado:", font=ctk.CTkFont(*FONT_UI), text_color=C["sub"]).pack(side="left")
        self.status_lbl = ctk.CTkLabel(srow, text="Verificando…",
                                       font=ctk.CTkFont("Segoe UI Semibold", 12), text_color=C["warn"])
        self.status_lbl.pack(side="left", padx=8)
        self.cloudflared_lbl = ctk.CTkLabel(srow, text="cloudflared: —",
                                            font=ctk.CTkFont(*FONT_UI), text_color=C["sub"])
        self.cloudflared_lbl.pack(side="left", padx=16)

        brow = ctk.CTkFrame(top, fg_color="transparent")
        brow.pack(fill="x", padx=10, pady=(4, 10))
        self.btn_start = btn(brow, "Iniciar", self.app.actions.tunnel_start, "ok", icon="play")
        self.btn_stop = btn(brow, "Detener", self.app.actions.tunnel_stop, "err", icon="stop", state="disabled")
        btn(brow, "Reiniciar", self.app.actions.tunnel_restart, "border", icon="refresh").pack(side="left", padx=4)
        btn(brow, "Validar config", self._validate, "border", icon="flask").pack(side="left", padx=4)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop.pack(side="left", padx=4)

        # ── Servicio de Windows (opcional) ──
        svc = card(parent)
        svc.grid(row=1, column=0, sticky="ew", padx=6, pady=3)
        h2(svc, "Servicio de Windows (opcional)").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(svc, text="El túnel ya funciona con «Iniciar»; el servicio solo si quieres "
                               "arranque automático sin abrir la app.",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["sub"], wraplength=640,
                     justify="left", anchor="w").pack(anchor="w", padx=14)
        srow2 = ctk.CTkFrame(svc, fg_color="transparent")
        srow2.pack(fill="x", padx=14, pady=(6, 4))
        ctk.CTkLabel(srow2, text="Estado:", font=ctk.CTkFont(*FONT_UI), text_color=C["sub"]).pack(side="left")
        self.svc_lbl = ctk.CTkLabel(srow2, text="—", font=ctk.CTkFont(*FONT_UI), text_color=C["info"])
        self.svc_lbl.pack(side="left", padx=8)
        irow = ctk.CTkFrame(svc, fg_color="transparent")
        irow.pack(fill="x", padx=10, pady=(2, 10))
        btn(irow, "Install Service", self._svc_install, "info").pack(side="left", padx=4)
        btn(irow, "Uninstall Service", self._svc_uninstall, "border").pack(side="left", padx=4)
        btn(irow, "Iniciar Servicio", self._svc_start, "ok", icon="play").pack(side="left", padx=4)
        btn(irow, "Detener Servicio", self._svc_stop, "err", icon="stop").pack(side="left", padx=4)

        # ── Config runtime ──
        cfg_card = card(parent)
        cfg_card.grid(row=2, column=0, sticky="nsew", padx=6, pady=(3, 6))
        cfg_card.columnconfigure(0, weight=1)
        cfg_card.rowconfigure(1, weight=1)
        h2(cfg_card, "Config runtime (generada en %ProgramData%\\Meshweave\\runtime)") \
            .grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.cfg_box = mono_box(cfg_card)
        self.cfg_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.cfg_box.configure(state="disabled")
        tag_configure(self.cfg_box)
        self._show_cfg()

    # ── Acciones ──

    def _show_cfg(self):
        ok, msg = prepare_runtime(load_config())
        self.cfg_box.configure(state="normal")
        self.cfg_box.delete("1.0", "end")
        from meshweave.paths import runtime_dir
        rt = runtime_dir() / "config.runtime.yml"
        if rt.exists():
            try:
                self.cfg_box.insert("1.0", rt.read_text(encoding="utf-8"))
            except OSError:
                self.cfg_box.insert("1.0", f"(no se pudo leer {rt})")
        else:
            self.cfg_box.insert("1.0", f"(aún no generada — {msg})")
        self.cfg_box.configure(state="disabled")

    def _validate(self):
        ok, msg = prepare_runtime(load_config())
        self.app.toast(f"Validar config: {msg}", "ok" if ok else "err")

    def _svc_install(self):
        ok, msg = self.app.actions.service_install()
        self.app.toast(msg, "ok" if ok else "err")
        self.refresh()

    def _svc_uninstall(self):
        ok, msg = self.app.actions.service_uninstall()
        self.app.toast(msg, "ok" if ok else "err")
        self.refresh()

    def _svc_start(self):
        ok, msg = self.app.actions.service_start()
        self.app.toast(msg, "ok" if ok else "err")
        self.refresh()

    def _svc_stop(self):
        ok, msg = self.app.actions.service_stop()
        self.app.toast(msg, "ok" if ok else "err")
        self.refresh()

    def refresh(self):
        tunnel = self.app.tunnel
        running = tunnel.running
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.status_lbl.configure(
            text="Conectado" if running else "Detenido",
            text_color=C["ok"] if running else C["muted"])
        ver = cloudflared_manager.installed_version()
        self.cloudflared_lbl.configure(
            text=f"cloudflared: {ver or 'NO INSTALADO'}"
                 + (" (descárgalo en Diagnóstico)" if not ver else ""),
            text_color=C["ok"] if ver else C["err"])
        self.svc_lbl.configure(text=cloudflared_service_status())
        self._show_cfg()
