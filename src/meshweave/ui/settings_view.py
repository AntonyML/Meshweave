"""Pestaña Configuración: edición segura de la configuración pública.

Los secretos (TunnelSecret, password de la nube) se escriben en DPAPI,
nunca en config.json. Los valores se guardan de forma atómica.
"""
from __future__ import annotations

import customtkinter as ctk

from meshweave.config import load_config, save_config
from meshweave.secrets import SecretStore
from meshweave.ui.theme import C, FONT_UI
from meshweave.ui.widgets import btn, card, h2


class SettingsView:
    def __init__(self, parent, app):
        self.app = app
        self.fields: dict[str, ctk.CTkEntry] = {}
        self.checks: dict[str, ctk.BooleanVar] = {}
        self._build(parent)

    def _entry(self, parent, row, label, key, cfg, secret=False):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(r, text=label, width=210, font=ctk.CTkFont(*FONT_UI),
                     text_color=C["sub"], anchor="w").pack(side="left")
        e = ctk.CTkEntry(r, show="*" if secret else "")
        e.pack(side="left", fill="x", expand=True, padx=4)
        e.insert(0, str(cfg.get(key, "") or ""))
        self.fields[key] = e

    def _check(self, parent, label, key, cfg):
        var = ctk.BooleanVar(value=bool(cfg.get(key, True)))
        ctk.CTkCheckBox(parent, text=label, variable=var,
                        font=ctk.CTkFont(*FONT_UI)).pack(anchor="w", padx=14, pady=2)
        self.checks[key] = var

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        cfg = load_config()

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(6, 3))

        # ── Túnel ──
        c1 = card(scroll)
        c1.pack(fill="x", padx=4, pady=(0, 6))
        h2(c1, "Túnel Cloudflare").pack(anchor="w", padx=14, pady=(10, 4))
        self._entry(c1, 0, "Hostname", "tunnel_hostname", cfg)
        self._entry(c1, 1, "Puerto local", "tunnel_local_port", cfg)
        self._entry(c1, 2, "Tunnel ID", "tunnel_id", cfg)
        self._entry(c1, 3, "Account Tag", "account_tag", cfg)
        self._entry(c1, 4, "TunnelSecret (DPAPI)", "tunnel_secret_dpapi", {}, secret=True)

        # ── Backend ──
        c2 = card(scroll)
        c2.pack(fill="x", padx=4, pady=(0, 6))
        h2(c2, "Backend").pack(anchor="w", padx=14, pady=(10, 4))
        self._entry(c2, 0, "Carpeta del proyecto", "backend_project_dir", cfg)
        self._entry(c2, 1, "Comando (vacío = uvicorn)", "backend_command", cfg)
        self._entry(c2, 2, "Archivo .env (vacío = proyecto/.env)", "backend_env_file", cfg)

        # ── Supabase / Sync ──
        c3 = card(scroll)
        c3.pack(fill="x", padx=4, pady=(0, 6))
        h2(c3, "Supabase / Sync").pack(anchor="w", padx=14, pady=(10, 4))
        self._entry(c3, 0, ".env del supabase local (Docker)", "supabase_env", cfg)
        self._entry(c3, 1, "Nube host (pooler)", "cloud_db_host", cfg)
        self._entry(c3, 2, "Nube usuario", "cloud_db_user", cfg)
        self._entry(c3, 3, "Nube puerto", "cloud_db_port", cfg)
        self._entry(c3, 4, "Nube db", "cloud_db_name", cfg)
        self._entry(c3, 5, "Nube password (DPAPI)", "cloud_db_password_dpapi", {}, secret=True)
        self._entry(c3, 6, "Lote (filas)", "batch_size", cfg)
        self._entry(c3, 7, "Delay entre lotes (s)", "batch_delay_seconds", cfg)

        # ── Horarios ──
        c4 = card(scroll)
        c4.pack(fill="x", padx=4, pady=(0, 6))
        h2(c4, "Horarios").pack(anchor="w", padx=14, pady=(10, 4))
        self._entry(c4, 0, "Sync (HH:MM)", "schedule_time", cfg)
        self._entry(c4, 1, "Backup (HH:MM)", "backup_time", cfg)
        self._entry(c4, 2, "Retención (días)", "backup_retention_days", cfg)

        # ── Alertas ──
        c5 = card(scroll)
        c5.pack(fill="x", padx=4, pady=(0, 6))
        h2(c5, "Alertas (Resend)").pack(anchor="w", padx=14, pady=(10, 4))
        self._entry(c5, 0, "From (vacío = .env backend)", "resend_from_email", cfg)
        self._entry(c5, 1, "To (vacío = ADMIN_EMAIL)", "alerts_to_email", cfg)
        self._check(c5, "Alertar en error", "alert_on_error", cfg)
        self._check(c5, "Alertar en partial", "alert_on_partial", cfg)
        self._check(c5, "Resumen diario (sync OK)", "summary_email", cfg)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        btn(bar, "💾  Guardar configuración", self._save, "ok").pack(side="left", padx=4)
        btn(bar, "🔄  Recargar", self._reload, "border").pack(side="left", padx=4)
        self.msg = ctk.CTkLabel(bar, text="", text_color=C["info"])
        self.msg.pack(side="left", padx=10)

    def _save(self):
        cfg = load_config()
        ints = ("tunnel_local_port", "cloud_db_port", "batch_size")
        floats = ("batch_delay_seconds",)
        secrets = SecretStore()
        for key, entry in self.fields.items():
            value = entry.get().strip()
            if key.endswith("_dpapi"):
                real = key.replace("_dpapi", "")
                if value:
                    secrets.set(real, value)
                    entry.delete(0, "end")
                continue
            if key in ints:
                try:
                    value = int(value or 0)
                except ValueError:
                    self.msg.configure(text=f"Valor inválido para {key}", text_color=C["err"])
                    return
            elif key in floats:
                try:
                    value = float(value or 0)
                except ValueError:
                    self.msg.configure(text=f"Valor inválido para {key}", text_color=C["err"])
                    return
            cfg[key] = value
        for key, var in self.checks.items():
            cfg[key] = bool(var.get())
        save_config(cfg)
        self.msg.configure(text="Configuración guardada (atómica + respaldo .bak)", text_color=C["ok"])
        self.app.actions.sync_refresh()

    def _reload(self):
        """Recarga los valores desde config.json (sin reconstruir la pestaña)."""
        cfg = load_config()
        for key, entry in self.fields.items():
            if key.endswith("_dpapi"):
                entry.delete(0, "end")  # los secretos no se muestran
                continue
            entry.delete(0, "end")
            entry.insert(0, str(cfg.get(key, "") or ""))
        for key, var in self.checks.items():
            var.set(bool(cfg.get(key, True)))
        self.msg.configure(text="Valores recargados", text_color=C["info"])
