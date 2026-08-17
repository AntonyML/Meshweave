"""Pestaña Configuración: edición segura de la configuración pública.

Los secretos (TunnelSecret, password de la nube) se escriben en DPAPI,
nunca en config.json. Los valores se guardan de forma atómica.
"""
from __future__ import annotations

import customtkinter as ctk

from meshweave.config import load_config, save_config
from meshweave.secrets import SecretStore
from meshweave.ui import icons
from meshweave.ui.theme import FONT_UI, C
from meshweave.ui.widgets import btn, card, h2

FONT_HINT = ("Segoe UI", 11)
_PLACEHOLDERS = {
    "tunnel_hostname": "app.ejemplo.com",
    "tunnel_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "account_tag": "Identificador de cuenta",
    "supabase_env": r"C:\ruta\supabase\.env",
    "cloud_db_host": "aws-0-xx.pooler.supabase.com",
    "cloud_db_user": "postgres.<project-ref>",
    "cloud_db_port": "5432",
    "cloud_db_name": "postgres",
    "resend_api_key": "re_...",
    "resend_from_email": "alerts@tu-dominio.com",
    "alerts_to_email": "tu@email.com",
}

# Guía en lenguaje natural para cada campo de configuración.
_HINTS: dict[str, str] = {
    # ── Túnel ──
    "tunnel_hostname": "Tu dominio público del túnel (p.ej. app.midominio.com). Es la URL que usan los usuarios para llegar a tu backend.",
    "tunnel_local_port": "Puerto local donde escucha tu backend (8000 por defecto). El túnel reenvía el tráfico del hostname a este puerto.",
    "tunnel_id": "ID del túnel (UUID). Lo ves en Cloudflare Zero Trust → Networks → Tunnels, en el detalle del túnel.",
    "account_tag": "Identificador corto de tu cuenta Cloudflare (aparece en la URL del dashboard de Zero Trust).",
    "tunnel_secret_dpapi": "Token del túnel. En Cloudflare → Zero Trust → Networks → Tunnels → tu túnel → Configure → copia el valor de --token en el comando cloudflared tunnel run. Cloudflare lo genera al crear el túnel; tú solo lo copias.",
    "resend_api_key": "Tu API key de resend.com (re_…). La encuentras en resend.com → API Keys.",
    # ── Backend ──
    "backend_project_dir": "Carpeta raíz del proyecto backend (donde está app/main.py). Vacío = Meshweave no gestiona el backend.",
    "backend_command": "Comando para arrancar el backend. Vacío = uvicorn app.main:app en el puerto del túnel.",
    # ── Supabase / Sync ──
    "supabase_env": "Ruta al archivo .env de tu Supabase local (Docker). Se usa para conectar a la base local y arrancar el sync.",
    "cloud_db_host": "Host del pooler de la nube, p.ej. db.xxxx.supabase.co:5432 (o aws-0-xx.pooler.supabase.com).",
    "cloud_db_user": "Usuario de la base en la nube (p.ej. postgres, o postgres.<ref> con pooler).",
    "cloud_db_port": "Puerto de conexión: 5432 (directo) o 6543 (pooler transaction).",
    "cloud_db_name": "Nombre de la base de datos en la nube (p.ej. postgres).",
    "cloud_db_password_dpapi": "Contraseña de la base en la nube (la del pooler). Se guarda cifrada con DPAPI.",
    "batch_size": "Filas procesadas por lote durante el sync. Baja el número si tienes tablas muy grandes o poca RAM.",
    "batch_delay_seconds": "Pausa en segundos entre lote y lote. Sube el valor si el sync consume demasiada CPU o red.",
    # ── Horarios ──
    "schedule_time": "Hora diaria del sync (formato HH:MM, 24 h). P.ej. 01:00. Requiere instalar las tareas en Sincronización.",
    "backup_time": "Hora diaria del backup del dump de la nube (HH:MM). P.ej. 01:30.",
    "backup_retention_days": "Cuántos días se conservan los dumps locales antes de borrarse automáticamente.",
    # ── Alertas ──
    "resend_from_email": "Remitente verificado en Resend (p.ej. alerts@tudominio.com). Se configura aquí y no se lee de ningún .env.",
    "alerts_to_email": "Tu email: aquí llegan los avisos si el sync o el backup fallan. Se configura aquí y no se lee de ningún .env.",
    "alert_on_error": "Email cuando una corrida falla por completo.",
    "alert_on_partial": "Email cuando la corrida termina con errores parciales (algunas tablas fallaron).",
    "summary_email": "Resumen diario por email cuando el sync termina sin errores.",
}

# Intro de una línea para cada tarjeta de sección.
_CARD_INTROS: dict[str, str] = {
    "Túnel Cloudflare": "Expone tu backend en internet con un dominio propio vía Cloudflare (gratis). Datos en Zero Trust → Networks → Tunnels.",
    "Backend": "Opcional: para que Meshweave arranque y vigile tu backend FastAPI automáticamente.",
    "Supabase / Sync": "Conexiones para sincronizar la base local (Docker) con la nube de Supabase.",
    "Horarios": "Tareas del programador de Windows. Se activan en Sincronización → «Instalar tareas».",
    "Alertas (Resend)": "Avisos por email si algo falla.",
}


class SettingsView:
    def __init__(self, parent, app):
        self.app = app
        self.fields: dict[str, ctk.CTkEntry] = {}
        self.checks: dict[str, ctk.BooleanVar] = {}
        self._build(parent)

    def _entry(self, parent, row, label, key, cfg, secret=False, required=False):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", padx=12, pady=(4, 2))
        r = ctk.CTkFrame(box, fg_color="transparent")
        r.pack(fill="x")
        lab = ctk.CTkLabel(r, text=label + (" *" if required else ""), width=210, font=ctk.CTkFont(*FONT_UI),
                     text_color=C["err"] if required else C["sub"], anchor="w")
        lab.pack(side="left")
        e = ctk.CTkEntry(r, show="*" if secret else "", fg_color="#ffffff",
                         text_color=C["text"], border_color=C["border"],
                         placeholder_text=_PLACEHOLDERS.get(key, ""),
                         placeholder_text_color=C["muted"])
        e.pack(side="left", fill="x", expand=True, padx=4)
        e.insert(0, str(cfg.get(key, "") or ""))
        self.fields[key] = e
        if secret:
            # Ojo para revelar/ocultar el valor (por defecto siempre oculto).
            eye = btn(r, "", None, "border", icon="eye", width=34, height=28)
            eye.pack(side="left", padx=(0, 4))

            def _toggle():
                masked = e.cget("show") == "*"
                e.configure(show="" if masked else "*")
                eye.configure(image=icons.photo("eye-off" if masked else "eye", 16))

            eye.configure(command=_toggle)
        self._hint(box, _HINTS.get(key, ""))

    def _check(self, parent, label, key, cfg):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", padx=12, pady=2)
        var = ctk.BooleanVar(value=bool(cfg.get(key, True)))
        ctk.CTkCheckBox(box, text=label, variable=var,
                        font=ctk.CTkFont(*FONT_UI)).pack(anchor="w")
        self.checks[key] = var
        self._hint(box, _HINTS.get(key, ""), indent=26)

    @staticmethod
    def _hint(parent, text: str, indent: int = 214):
        """Subtítulo explicativo bajo un campo (vacío = sin guía)."""
        if not text:
            return
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(*FONT_HINT),
                     text_color=C["muted"], anchor="w", justify="left",
                     wraplength=600).pack(anchor="w", padx=(indent, 0), pady=(0, 2))

    @staticmethod
    def _card_intro(parent, text: str):
        """Intro de una línea bajo el título de una sección."""
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(*FONT_HINT),
                     text_color=C["sub"], anchor="w", justify="left",
                     wraplength=840).pack(anchor="w", padx=14, pady=(0, 6))

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        cfg = load_config()

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=(6, 3))

        # ── Túnel ──
        c1 = card(scroll)
        c1.pack(fill="x", padx=4, pady=(0, 6))
        h2(c1, "Túnel Cloudflare").pack(anchor="w", padx=14, pady=(10, 4))
        self._card_intro(c1, _CARD_INTROS["Túnel Cloudflare"])
        self._entry(c1, 0, "Hostname", "tunnel_hostname", cfg, required=True)
        self._entry(c1, 1, "Puerto local", "tunnel_local_port", cfg)
        self._entry(c1, 2, "Tunnel ID", "tunnel_id", cfg, required=True)
        self._entry(c1, 3, "Account Tag", "account_tag", cfg, required=True)
        self._entry(c1, 4, "TunnelSecret (DPAPI)", "tunnel_secret_dpapi", {}, secret=True, required=True)
        ctk.CTkLabel(c1, text="¿Cómo obtenerlo? →", text_color=C["accent"], cursor="hand2").pack(anchor="w", padx=224)
        c1.winfo_children()[-1].bind("<Button-1>", lambda _e: __import__("webbrowser").open("https://dash.cloudflare.com"))

        # ── Supabase / Sync ──
        c3 = card(scroll)
        c3.pack(fill="x", padx=4, pady=(0, 6))
        h2(c3, "Supabase / Sync").pack(anchor="w", padx=14, pady=(10, 4))
        self._card_intro(c3, _CARD_INTROS["Supabase / Sync"])
        self._entry(c3, 0, ".env del supabase local (Docker)", "supabase_env", cfg, required=True)
        self._entry(c3, 1, "Nube host (pooler)", "cloud_db_host", cfg, required=True)
        self._entry(c3, 2, "Nube usuario", "cloud_db_user", cfg, required=True)
        self._entry(c3, 3, "Nube puerto", "cloud_db_port", cfg)
        self._entry(c3, 4, "Nube db", "cloud_db_name", cfg)
        self._entry(c3, 5, "Nube password (DPAPI)", "cloud_db_password_dpapi", {}, secret=True, required=True)
        self._entry(c3, 6, "Lote (filas)", "batch_size", cfg)
        self._entry(c3, 7, "Delay entre lotes (s)", "batch_delay_seconds", cfg)

        # ── Horarios ──
        c4 = card(scroll)
        c4.pack(fill="x", padx=4, pady=(0, 6))
        h2(c4, "Horarios").pack(anchor="w", padx=14, pady=(10, 4))
        self._card_intro(c4, _CARD_INTROS["Horarios"])
        self._entry(c4, 0, "Sync (HH:MM)", "schedule_time", cfg)
        self._entry(c4, 1, "Backup (HH:MM)", "backup_time", cfg)
        self._entry(c4, 2, "Retención (días)", "backup_retention_days", cfg)

        # ── Alertas ──
        c5 = card(scroll)
        c5.pack(fill="x", padx=4, pady=(0, 6))
        h2(c5, "Alertas (Resend)").pack(anchor="w", padx=14, pady=(10, 4))
        self._card_intro(c5, _CARD_INTROS["Alertas (Resend)"])
        self._entry(c5, 0, "API key", "resend_api_key", cfg, secret=True, required=True)
        self._entry(c5, 1, "From", "resend_from_email", cfg, required=True)
        self._entry(c5, 2, "To", "alerts_to_email", cfg, required=True)
        self._check(c5, "Alertar en error", "alert_on_error", cfg)
        self._check(c5, "Alertar en partial", "alert_on_partial", cfg)
        self._check(c5, "Resumen diario (sync OK)", "summary_email", cfg)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        btn(bar, "Guardar configuración", self._save, "ok", icon="save").pack(side="left", padx=4)
        btn(bar, "Recargar", self._reload, "border", icon="refresh").pack(side="left", padx=4)
        self.msg = ctk.CTkLabel(bar, text="", text_color=C["info"])
        self.msg.pack(side="left", padx=10)

    def _save(self):
        cfg = load_config()
        required = ("tunnel_hostname", "tunnel_id", "account_tag", "tunnel_secret_dpapi", "supabase_env", "cloud_db_host", "cloud_db_user", "cloud_db_password_dpapi", "resend_api_key", "resend_from_email", "alerts_to_email")
        secret_store = SecretStore()
        for key in required:
            if key in ("tunnel_secret_dpapi", "cloud_db_password_dpapi", "resend_api_key"):
                present = bool(self.fields[key].get().strip()) or secret_store.has(key.replace("_dpapi", ""))
            else:
                present = bool(self.fields[key].get().strip())
            if not present:
                self.fields[key].focus_set()
                self.msg.configure(text=f"Falta el campo obligatorio: {key}", text_color=C["err"])
                return
        ints = ("tunnel_local_port", "cloud_db_port", "batch_size")
        floats = ("batch_delay_seconds",)
        secrets = SecretStore()
        for key, entry in self.fields.items():
            value = entry.get().strip()
            if key.endswith("_dpapi") or key == "resend_api_key":
                real = key.replace("_dpapi", "")
                if value:
                    secrets.set(real, value)
                    entry.delete(0, "end")
                cfg.pop(key, None)
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
            if key.endswith("_dpapi") or key == "resend_api_key":
                entry.delete(0, "end")  # los secretos no se muestran
                continue
            entry.delete(0, "end")
            entry.insert(0, str(cfg.get(key, "") or ""))
        for key, var in self.checks.items():
            var.set(bool(cfg.get(key, True)))
        self.msg.configure(text="Valores recargados", text_color=C["info"])
