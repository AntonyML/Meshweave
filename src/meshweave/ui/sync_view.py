"""Pestaña Sincronización: estado, controles, historial, watermarks y log en vivo."""
from __future__ import annotations

import customtkinter as ctk

from meshweave.ui.theme import FONT_MONO, FONT_UI, C
from meshweave.ui.widgets import append_line, btn, card, h2, mono_box, tag_configure


class SyncView:
    def __init__(self, parent, app):
        self.app = app
        self._busy = False
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)

        est = card(parent)
        est.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 3))
        h2(est, "Sync Docker → Nube (nocturno)").pack(anchor="w", padx=14, pady=(10, 4))
        self.status_lbl = ctk.CTkLabel(est, text="Cargando…",
                                       font=ctk.CTkFont("Segoe UI Semibold", 13),
                                       text_color=C["muted"], anchor="w")
        self.status_lbl.pack(fill="x", padx=14, pady=(0, 2))
        self.meta_lbl = ctk.CTkLabel(est, text="", font=ctk.CTkFont(*FONT_MONO),
                                     text_color=C["sub"], anchor="w", justify="left")
        self.meta_lbl.pack(fill="x", padx=14, pady=(0, 2))
        self.task_lbl = ctk.CTkLabel(est, text="Tarea: …", font=ctk.CTkFont(*FONT_UI),
                                     text_color=C["sub"], anchor="w")
        self.task_lbl.pack(fill="x", padx=14, pady=(0, 10))

        ctrl = card(parent)
        ctrl.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=3)
        h2(ctrl, "Controles").pack(anchor="w", padx=14, pady=(10, 6))
        brow = ctk.CTkFrame(ctrl, fg_color="transparent")
        brow.pack(fill="x", padx=10, pady=(0, 6))
        self.btn_run = btn(brow, "Sincronizar ahora", self.app.actions.sync_now, "ok", icon="play")
        self.btn_check = btn(brow, "Probar conexiones", self.app.actions.sync_check, "border", icon="flask")
        self.btn_refresh = btn(brow, "Actualizar estado", self.app.actions.sync_refresh, "info", icon="refresh")
        self.btn_install = btn(brow, "Instalar tareas", self.app.actions.sync_install_tasks, "border", icon="calendar")
        self.btn_uninstall = btn(brow, "Quitar tareas", self.app.actions.sync_uninstall_tasks, "err", icon="trash")
        self.btn_alert = btn(brow, "Probar alerta", self.app.actions.sync_test_alert, "border", icon="mail")
        for b in (self.btn_run, self.btn_check, self.btn_refresh, self.btn_install,
                  self.btn_uninstall, self.btn_alert):
            b.pack(side="left", padx=4, ipady=2)
        ctk.CTkLabel(ctrl, text="Incremental (solo filas cambiadas), lotes con delay y backoff — "
                                "cuidadoso con el free tier. Nunca borra en la nube (backup conservador).",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["sub"], anchor="w", wraplength=880,
                     ).pack(anchor="w", padx=14, pady=(0, 10))

        hist = card(parent)
        hist.grid(row=2, column=0, sticky="nsew", padx=(6, 3), pady=3)
        hist.columnconfigure(0, weight=1)
        hist.rowconfigure(1, weight=1)
        h2(hist, "Historial (últimas corridas)").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.history = mono_box(hist)
        self.history.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.history.configure(state="disabled")

        wm = card(parent)
        wm.grid(row=2, column=1, sticky="nsew", padx=(3, 6), pady=3)
        wm.columnconfigure(0, weight=1)
        wm.rowconfigure(1, weight=1)
        h2(wm, "Watermarks por tabla").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.watermarks = mono_box(wm)
        self.watermarks.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.watermarks.configure(state="disabled")

        lc = card(parent)
        lc.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=6, pady=(3, 6))
        lc.columnconfigure(0, weight=1)
        lc.rowconfigure(1, weight=1)
        lrow = ctk.CTkFrame(lc, fg_color="transparent")
        lrow.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        h2(lrow, "Log en vivo").pack(side="left", padx=4)
        self.autoscroll = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(lrow, text="Auto-scroll", variable=self.autoscroll,
                        font=ctk.CTkFont(*FONT_UI)).pack(side="right", padx=6)
        self.logbox = mono_box(lc)
        self.logbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.logbox.configure(state="disabled")
        tag_configure(self.logbox)

    # ── API para la app ──

    def set_busy(self, busy: bool):
        self._busy = busy
        self.btn_run.configure(state="disabled" if busy else "normal",
                               text="Sincronizando…" if busy else "Sincronizar ahora")

    def append(self, line: str, level: str = "info"):
        append_line(self.logbox, line, level, autoscroll=self.autoscroll.get())

    def apply_state(self, data: dict):
        cfg = data.get("cfg", {})
        state = data.get("state", {})
        runs = data.get("runs", [])
        alert = data.get("alert")
        task = data.get("sync_task", "—")
        backup_task = data.get("backup_task", "—")

        last = state.get("last_run") or {}
        status = last.get("status") or "sin corridas"
        color = {"ok": C["ok"], "partial": C["warn"], "error": C["err"]}.get(status, C["muted"])
        self.status_lbl.configure(text=f"Última corrida: {status} | inicio: {last.get('started_at', '—')}",
                                  text_color=color)
        meta = f"  fin: {last.get('finished_at', '—')}"
        if last.get("error"):
            meta += f"\n  error: {last['error']}"
        meta += f"\n  próxima corrida: {cfg.get('schedule_time', '01:00')} (diaria) | backup: {cfg.get('backup_time', '01:30')}"
        self.meta_lbl.configure(text=meta)
        summary_on = "sí" if cfg.get("summary_email", True) else "no"
        if alert:
            alert_text = f"Alertas: activas → {alert['to']} (Resend) | resumen diario: {summary_on}"
        else:
            alert_text = "Alertas: DESACTIVADAS (configura Resend en Configuración)"
        self.task_lbl.configure(text=f"Tarea sync: {task}  |  Tarea backup: {backup_task}  |  {alert_text}")

        lines = []
        for r in runs:
            err = r.get("error") or ""
            lines.append(f"{str(r.get('started_at', '—'))[:19]}  {str(r.get('status', '?')):8s}  "
                         f"{r.get('total_rows', 0):5d} filas  {r.get('duration_s', 0):6.1f}s  {err}")
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.insert("1.0", "\n".join(lines) or "(sin corridas todavía)")
        self.history.configure(state="disabled")

        wm = state.get("watermarks", {})
        wlines = []
        for t in sorted(wm):
            w = wm[t]
            wlines.append(f"{t:28s} {w.get('updated_at', '—') if isinstance(w, dict) else w}")
        self.watermarks.configure(state="normal")
        self.watermarks.delete("1.0", "end")
        self.watermarks.insert("1.0", "\n".join(wlines) or "(sin watermarks)")
        self.watermarks.configure(state="disabled")
