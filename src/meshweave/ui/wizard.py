"""Asistente de primera configuración de Meshweave.

Se muestra la primera vez (config vacía) y guía por: bienvenida + cloudflared,
túnel Cloudflare, backend (opcional), Supabase (local + nube), alertas y
tareas. Los secretos se escriben en DPAPI; el resto en config.json.

Los valores se conservan al cambiar de paso (self.values) — al finalizar se
guardan TODOS, no solo los del último paso.
"""
from __future__ import annotations

import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from meshweave.config import load_config, save_config
from meshweave.secrets import SecretStore
from meshweave.ui.theme import FONT_UI, C
from meshweave.ui.widgets import btn, card, h2

# (label, clave, secreto, placeholder)
_STEPS: dict[int, list[tuple[str, str, bool, str]]] = {
    1: [
        ("Hostname", "tunnel_hostname", False, "p.ej. app.midominio.com"),
        ("Puerto local", "tunnel_local_port", False, "8000"),
        ("Tunnel ID", "tunnel_id", False, ""),
        ("Account Tag", "account_tag", False, ""),
        ("TunnelSecret", "tunnel_secret", True, ""),
    ],
    2: [
        ("Carpeta del proyecto", "backend_project_dir", False, ""),
        ("Comando (vacío = uvicorn)", "backend_command", False, ""),
    ],
    3: [
        (".env supabase local", "supabase_env", False, "ruta al .env de Docker"),
        ("Nube host (pooler)", "cloud_db_host", False, ""),
        ("Nube usuario", "cloud_db_user", False, ""),
        ("Nube puerto", "cloud_db_port", False, "5432"),
        ("Nube db", "cloud_db_name", False, "postgres"),
        ("Nube password", "cloud_db_password", True, ""),
    ],
    4: [
        ("Remitente (from)", "resend_from_email", False, "vacío = .env del backend"),
        ("Destinatario (to)", "alerts_to_email", False, ""),
    ],
}


def _field(parent, label: str, key: str, secret: bool, placeholder: str,
           width: int = 300) -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=6, pady=3)
    ctk.CTkLabel(row, text=label, width=190, font=ctk.CTkFont(*FONT_UI),
                 text_color=C["sub"], anchor="w").pack(side="left")
    entry = ctk.CTkEntry(row, show="*" if secret else "", width=width,
                         placeholder_text=placeholder)
    entry.pack(side="left", padx=4, fill="x", expand=True)
    entry._mesh_key = key
    return entry


class FirstRunWizard(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Bienvenido a Meshweave")
        self.geometry("660x580")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.fields: dict[str, ctk.CTkEntry] = {}
        self.checks: dict[str, ctk.BooleanVar] = {}
        self.values: dict[str, object] = {}  # valores persistentes entre pasos
        self._step = 0
        self._finished = False
        self.cfg = load_config()

        self._build()
        self._show_step(0)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ── Estructura ────────────────────────────────────────────────────────

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=C["darker"], corner_radius=0)
        hdr.pack(fill="x")
        h2(hdr, "⬡  Bienvenido a Meshweave").pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(hdr, text="Primera configuración — tus datos quedan en esta PC "
                               "(secretos cifrados con DPAPI).",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["sub"]).pack(anchor="w", padx=18, pady=(0, 12))

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=12, pady=(6, 0))

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=14, pady=10)
        self.step_lbl = ctk.CTkLabel(nav, text="", font=ctk.CTkFont(*FONT_UI),
                                     text_color=C["muted"])
        self.step_lbl.pack(side="left")
        self.btn_prev = btn(nav, "← Anterior", self._prev, "border")
        self.btn_prev.pack(side="right", padx=4)
        self.btn_next = btn(nav, "Siguiente →", self._next, "info")
        self.btn_next.pack(side="right", padx=4)

    # ── Pasos ─────────────────────────────────────────────────────────────

    def _capture(self):
        """Guarda los valores actuales ANTES de destruir los widgets del paso."""
        for key, entry in self.fields.items():
            self.values[key] = entry.get()
        for key, var in self.checks.items():
            self.values[key] = bool(var.get())

    def _clear_body(self):
        self._capture()
        for w in self.body.winfo_children():
            w.destroy()
        self.fields.clear()
        self.checks.clear()

    def _restore(self, key: str, entry: ctk.CTkEntry):
        value = self.values.get(key)
        if value is None:
            return
        entry.insert(0, str(value))

    def _show_step(self, idx: int):
        self._clear_body()
        self._step = idx
        self.step_lbl.configure(text=f"Paso {idx + 1} de 6")
        self.btn_prev.configure(state="normal" if idx > 0 else "disabled")
        if idx == 0:
            self._step_welcome()
        elif idx == 1:
            self._step_tunnel()
        elif idx == 2:
            self._step_backend()
        elif idx == 3:
            self._step_supabase()
        elif idx == 4:
            self._step_alerts()
        else:
            self._step_tasks()
        self.btn_next.configure(text="Finalizar" if idx == 5 else "Siguiente →")

    def _step_welcome(self):
        card(self.body).pack(fill="x", pady=4)
        h2(self.body, "1/6 · Componentes requeridos").pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(self.body,
                     text="Meshweave gestiona el túnel Cloudflare, el backend, el sync "
                          "Docker → Supabase y los backups.\n\n"
                          "Falta el componente cloudflared (el túnel no puede arrancar sin él). "
                          "Puedes descargarlo ahora o elegir un archivo existente.",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["text"], wraplength=560,
                     justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0, 8))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 12))
        self.cf_lbl = ctk.CTkLabel(row, text="cloudflared: verificando…",
                                   font=ctk.CTkFont(*FONT_UI), text_color=C["warn"])
        self.cf_lbl.pack(side="left", padx=4)
        btn(row, "⬇  Descargar", self._download_cloudflared, "ok").pack(side="right", padx=4)
        btn(row, "📂  Usar existente", self._pick_cloudflared, "border").pack(side="right", padx=4)
        self._check_cloudflared()

    def _step_form(self, title: str, intro: str, keys: list[tuple[str, str, bool, str]],
                   extra=None):
        card(self.body).pack(fill="x", pady=4)
        h2(self.body, title).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(self.body, text=intro, font=ctk.CTkFont(*FONT_UI), text_color=C["sub"],
                     wraplength=560, justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0, 8))
        c = card(self.body)
        c.pack(fill="x", padx=8, pady=(0, 10))
        for label, key, secret, placeholder in keys:
            entry = _field(c, label, key, secret, placeholder)
            self.fields[key] = entry
            self._restore(key, entry)
        if extra:
            extra(c)

    def _step_tunnel(self):
        self._step_form(
            "2/6 · Túnel Cloudflare",
            "Datos de tu túnel en Cloudflare Zero Trust (Networks → Tunnels). "
            "El TunnelSecret se guarda cifrado (DPAPI).",
            _STEPS[1],
        )

    def _step_backend(self):
        def extra(c):
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=3)
            ctk.CTkLabel(row, text="", width=190).pack(side="left")
            btn(row, "📂 Buscar carpeta", self._browse_backend, "border").pack(side="left", padx=4)
        self._step_form(
            "3/6 · Backend FastAPI (opcional)",
            "Si Meshweave debe iniciar tu backend, indica la carpeta del proyecto. "
            "Puedes dejarlo vacío y configurarlo después.",
            _STEPS[2],
            extra=extra,
        )

    def _step_supabase(self):
        def extra(c):
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=3)
            ctk.CTkLabel(row, text="", width=190).pack(side="left")
            btn(row, "📂 Buscar .env", self._browse_env, "border").pack(side="left", padx=4)
        self._step_form(
            "4/6 · Supabase (local + nube)",
            "Ruta al .env de tu Supabase local (Docker) y datos del pooler de la nube. "
            "El password de la nube se guarda cifrado (DPAPI).",
            _STEPS[3],
            extra=extra,
        )

    def _step_alerts(self):
        def extra(c):
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(c, text="Enviar resumen diario cuando el sync termina OK",
                            variable=var, font=ctk.CTkFont(*FONT_UI)).pack(anchor="w", padx=12, pady=4)
            self.checks["summary_email"] = var
            btn(c, "📧 Probar alerta", self._test_alert, "border").pack(anchor="w", padx=12, pady=(2, 10))
        self._step_form(
            "5/6 · Alertas por email (Resend, opcional)",
            "Recibirás un email si el sync/backup falla y un resumen diario cuando todo va "
            "bien. Vacío = se toma del .env del backend.",
            _STEPS[4],
            extra=extra,
        )

    def _step_tasks(self):
        card(self.body).pack(fill="x", pady=4)
        h2(self.body, "6/6 · Tareas programadas").pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(self.body,
                     text="MeshweaveSyncService (sync diario 01:00) y MeshweaveBackupService "
                          "(backup del dump 01:30). Se recomienda instalarlas; si el PC está "
                          "apagado, corren al encender.",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["text"], wraplength=560,
                     justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0, 8))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 10))
        self.tasks_lbl = ctk.CTkLabel(row, text="Tareas: sin instalar",
                                      font=ctk.CTkFont(*FONT_UI), text_color=C["warn"])
        self.tasks_lbl.pack(side="left", padx=4)
        btn(row, "📅 Instalar tareas", self._install_tasks, "info").pack(side="right", padx=4)
        self._refresh_tasks()

    # ── Acciones ──────────────────────────────────────────────────────────

    def _post(self, fn) -> None:
        """Ejecuta en el hilo principal: vía App.post si existe, si no after()."""
        master = self.master
        if master is not None and hasattr(master, "post"):
            master.post(fn)
        else:
            self.after(0, fn)

    def _check_cloudflared(self):
        def _go():
            from meshweave.services import cloudflared_manager
            ver = cloudflared_manager.installed_version()
            self._post(lambda: self.cf_lbl.configure(
                text=f"cloudflared: {ver or 'NO instalado'}",
                text_color=C["ok"] if ver else C["err"]))
        threading.Thread(target=_go, daemon=True).start()

    def _download_cloudflared(self):
        self.cf_lbl.configure(text="Descargando cloudflared…", text_color=C["warn"])
        def _go():
            from meshweave.services import cloudflared_manager
            ok, msg = cloudflared_manager.download()
            self._post(lambda: self.cf_lbl.configure(
                text=msg, text_color=C["ok"] if ok else C["err"]))
        threading.Thread(target=_go, daemon=True).start()

    def _pick_cloudflared(self):
        path = filedialog.askopenfilename(
            title="Seleccionar cloudflared.exe", parent=self,
            filetypes=[("Ejecutable", "*.exe")])
        if not path:
            return
        import shutil

        from meshweave.paths import bin_dir
        try:
            bin_dir().mkdir(parents=True, exist_ok=True)
            dest = bin_dir() / "cloudflared.exe"
            shutil.copy2(path, dest)
            self.cf_lbl.configure(text=f"cloudflared copiado desde {path}", text_color=C["ok"])
        except OSError as e:
            self.cf_lbl.configure(text=f"No se pudo copiar: {e}", text_color=C["err"])

    def _browse_backend(self):
        path = filedialog.askdirectory(title="Carpeta del backend", parent=self)
        if path and "backend_project_dir" in self.fields:
            self.fields["backend_project_dir"].delete(0, "end")
            self.fields["backend_project_dir"].insert(0, path)

    def _browse_env(self):
        path = filedialog.askopenfilename(title="Seleccionar .env de supabase", parent=self)
        if path and "supabase_env" in self.fields:
            self.fields["supabase_env"].delete(0, "end")
            self.fields["supabase_env"].insert(0, path)

    def _test_alert(self):
        def _go():
            from meshweave.sync import send_test_alert
            res = send_test_alert(load_config())
            self._post(lambda: messagebox.showinfo(
                "Prueba de alerta", f"{res.get('status')} — {res.get('reason') or res.get('id') or ''}",
                parent=self))
        threading.Thread(target=_go, daemon=True).start()

    def _install_tasks(self):
        from meshweave.services import sync_service
        svc = sync_service.SyncService(lambda *a: None)
        ok, msg = svc.install_tasks()
        self._post(lambda: (self.tasks_lbl.configure(
            text=msg.splitlines()[0], text_color=C["ok"] if ok else C["err"]),
            messagebox.showinfo("Tareas", msg, parent=self)))

    def _refresh_tasks(self):
        from meshweave import windows_tasks
        cfg = load_config()
        self.tasks_lbl.configure(
            text=f"Sync: {windows_tasks.sync_task_status(cfg).split(': ', 1)[-1]}  |  "
                 f"Backup: {windows_tasks.backup_task_status(cfg).split(': ', 1)[-1]}")

    # ── Guardar ───────────────────────────────────────────────────────────

    def _finish(self):
        self._capture()  # captura también el último paso
        cfg = load_config()
        secrets = SecretStore()
        for key, value in self.values.items():
            if key in ("tunnel_secret", "cloud_db_password"):
                if isinstance(value, str) and value.strip():
                    secrets.set(key, value.strip())
                continue
            if isinstance(value, bool):
                cfg[key] = value
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue  # no pisar defaults con campos vacíos
                cfg[key] = value
            else:
                cfg[key] = value
        for int_key in ("tunnel_local_port", "cloud_db_port"):
            try:
                cfg[int_key] = int(cfg.get(int_key) or 0)
            except (TypeError, ValueError):
                pass
        save_config(cfg)
        self._finished = True
        self.destroy()

    def _next(self):
        if self._step == 5:
            self._finish()
        else:
            self._show_step(self._step + 1)

    def _prev(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    def _cancel(self):
        if not messagebox.askyesno("Salir", "¿Cancelar la configuración? Puedes completarla "
                                            "después en la pestaña Configuración.", parent=self):
            return
        self.destroy()


def run_first_run_wizard(master) -> bool:
    """Muestra el asistente (modal). Devuelve True si se completó."""
    wizard = FirstRunWizard(master)
    master.wait_window(wizard)
    return wizard._finished
