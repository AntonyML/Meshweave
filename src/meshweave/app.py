"""Meshweave — ventana principal.

La UI solo habla con servicios (tunnel/backend/sync) y recibe eventos por cola.
No toca subprocess, psycopg ni configs directamente.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading

import customtkinter as ctk

from meshweave import APP_NAME, __version__
from meshweave import sync as sync_mod
from meshweave.config import is_first_run, load_config, save_config
from meshweave.paths import ensure_dirs
from meshweave.services.backend_service import BackendService
from meshweave.services.sync_service import SyncService
from meshweave.services.tunnel_service import TunnelService
from meshweave.ui.backend_view import BackendView
from meshweave.ui.backups_view import BackupsView
from meshweave.ui.dashboard_view import DashboardView
from meshweave.ui.diagnostics_view import DiagnosticsView
from meshweave.ui.logs_view import LogsView
from meshweave.ui.settings_view import SettingsView
from meshweave.ui.sync_view import SyncView
from meshweave.ui.theme import FONT_MONO, FONT_UI, C
from meshweave.ui.tunnel_view import TunnelView


class Actions:
    """Comandos de la UI → servicios. Resultados vía toast/refresh/eventos."""

    def __init__(self, app):
        self.app = app

    # ── Túnel ──

    def tunnel_start(self):
        if self.app.tunnel.running:
            return
        def _go():
            cfg = load_config()
            ok, msg = self.app.tunnel.start(cfg)
            self.app.post(lambda: (self.app.toast(msg, "ok" if ok else "err"),
                                   self.app.refresh_views()))
        threading.Thread(target=_go, daemon=True).start()

    def tunnel_stop(self):
        def _go():
            ok, msg = self.app.tunnel.stop()
            self.app.post(lambda: (self.app.toast(msg, "ok" if ok else "err"),
                                   self.app.refresh_views()))
        threading.Thread(target=_go, daemon=True).start()

    def tunnel_restart(self):
        def _go():
            self.app.tunnel.stop()
            cfg = load_config()
            ok, msg = self.app.tunnel.start(cfg)
            self.app.post(lambda: (self.app.toast(msg, "ok" if ok else "err"),
                                   self.app.refresh_views()))
        threading.Thread(target=_go, daemon=True).start()

    # ── Servicio de Windows (cloudflared) ──

    def _svc(self, cmd: list[str]):
        def _go():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                out = (r.stdout or r.stderr or "").strip()
                self.app.post(lambda: self.app.toast(out or f"código {r.returncode}",
                                                     "ok" if r.returncode == 0 else "err"))
            except Exception as exc:  # noqa: BLE001
                err_msg = str(exc)
                self.app.post(lambda: self.app.toast(err_msg, "err"))
        threading.Thread(target=_go, daemon=True).start()

    def service_install(self) -> tuple[bool, str]:
        from meshweave.paths import runtime_dir
        from meshweave.services import cloudflared_manager
        from meshweave.services.tunnel_service import prepare_runtime
        ok, msg = prepare_runtime(load_config())
        if not ok:
            return False, msg
        exe = cloudflared_manager.binary_path()
        config_rt = runtime_dir() / "config.runtime.yml"
        bin_path = f'"{exe}" tunnel --config "{config_rt}" run'
        self._svc(["sc", "create", "cloudflared", f"binPath={bin_path}", "start=auto"])
        return True, "Instalando servicio…"

    def service_uninstall(self) -> tuple[bool, str]:
        self._svc(["sc", "stop", "cloudflared"])
        self._svc(["sc", "delete", "cloudflared"])
        return True, "Eliminando servicio…"

    def service_start(self) -> tuple[bool, str]:
        self._svc(["net", "start", "cloudflared"])
        return True, "Iniciando servicio…"

    def service_stop(self) -> tuple[bool, str]:
        self._svc(["net", "stop", "cloudflared"])
        return True, "Deteniendo servicio…"

    # ── Backend ──

    def backend_connect(self, project_dir: str) -> tuple[bool, str]:
        from pathlib import Path
        p = Path(project_dir)
        if not p.is_dir():
            return False, f"La carpeta no existe: {p}"
        if not (p / "app" / "main.py").exists():
            return False, "No parece un backend FastAPI válido (falta app/main.py)."
        try:
            cfg = load_config()
            cfg["backend_project_dir"] = str(p)
            save_config(cfg)
            return True, "Backend conectado y guardado en la configuración."
        except Exception as e:  # noqa: BLE001
            return False, f"Error guardando: {e}"

    def backend_start(self):
        def _go():
            cfg = load_config()
            project = cfg.get("backend_project_dir", "")
            ok, msg = self.app.backend.start(
                __import__("pathlib").Path(project),
                cfg.get("backend_command") or None,
            )
            self.app.post(lambda: (self.app.toast(msg, "ok" if ok else "err"),
                                   self.app.refresh_views()))
        threading.Thread(target=_go, daemon=True).start()

    def backend_stop(self):
        def _go():
            ok, msg = self.app.backend.stop()
            self.app.post(lambda: (self.app.toast(msg, "ok" if ok else "err"),
                                   self.app.refresh_views()))
        threading.Thread(target=_go, daemon=True).start()

    # ── Sync ──

    def sync_now(self):
        self.app.sync_view.set_busy(True)
        self.app.sync_view.append("▶ Sincronizando (incremental)…", "info")
        self.app.sync.run_now(emit=lambda msg, lvl: self.app._q.put(("sync", msg, lvl)))

    def sync_backup_now(self):
        self.app.backups_view.append("▶ Backup del dump de la nube…", "info")
        self.app.sync.run_backup(emit=lambda msg, lvl: (self.app._q.put(("sync", msg, lvl)),
                                                        self.app._q.put(("backup", msg, lvl))))

    def sync_check(self):
        def _go():
            try:
                cfg = load_config()
                res = sync_mod.check_connections(cfg)
                self.app._q.put(("sync", "Prueba de conexiones (solo lectura):", "info"))
                for name, info in res.items():
                    if info.get("ok"):
                        self.app._q.put(("sync", f"  {name}: PG {info['version']} | {info['size']}", "ok"))
                    else:
                        self.app._q.put(("sync", f"  {name}: ERROR {info.get('error', '')}", "err"))
            except Exception as e:  # noqa: BLE001
                self.app._q.put(("sync", f"ERROR probando conexiones: {e}", "error"))
        threading.Thread(target=_go, daemon=True).start()

    def sync_refresh(self):
        self.app.sync.refresh()

    def sync_install_tasks(self):
        def _go():
            ok, msg = self.app.sync.install_tasks()
            self.app.post(lambda: (self.app.toast(msg, "ok" if ok else "err"),
                                   self.app.sync.refresh()))
        threading.Thread(target=_go, daemon=True).start()

    def sync_uninstall_tasks(self):
        def _go():
            ok, msg = self.app.sync.uninstall_tasks()
            self.app.post(lambda: (self.app.toast(msg, "ok" if ok else "err"),
                                   self.app.sync.refresh()))
        threading.Thread(target=_go, daemon=True).start()

    def sync_test_alert(self):
        def _go():
            res = self.app.sync.test_alert()
            status, detail = res.get("status", "?"), res.get("reason") or res.get("id") or ""
            level = "err" if status == "error" else ("warn" if status == "skipped" else "ok")
            self.app._q.put(("sync", f"Alerta de prueba: {status} — {detail}", level))
        threading.Thread(target=_go, daemon=True).start()

    def sync_test_summary(self):
        def _go():
            res = self.app.sync.test_summary()
            status, detail = res.get("status", "?"), res.get("reason") or res.get("id") or ""
            level = "err" if status == "error" else ("warn" if status == "skipped" else "ok")
            self.app._q.put(("sync", f"Resumen de prueba: {status} — {detail}", level))
        threading.Thread(target=_go, daemon=True).start()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Centro de control local  v{__version__}")
        self.geometry("980x700")
        self.minsize(860, 600)

        self._q = queue.Queue()
        self.tunnel = TunnelService(lambda line: self._q.put(("tunnel", line)))
        self.backend = BackendService(lambda line: self._q.put(("backend", line)))
        self.sync = SyncService(self._on_sync_event)
        self.actions = Actions(self)

        self._build_header()
        self._build_tabs()
        self._toast_lbl = None
        self._poll()
        self.after(1500, self._initial_sync_refresh)

    def _initial_sync_refresh(self):
        if not getattr(self, "_destroyed", False):
            self.sync.refresh()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Cabecera ──

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=C["darker"], height=52, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"⬡  {APP_NAME}",
                     font=ctk.CTkFont("Segoe UI Semibold", 16),
                     text_color=C["info"]).pack(side="left", padx=20)
        cfg = load_config()
        ctk.CTkLabel(hdr, text=f"{cfg.get('tunnel_hostname', '—')}  →  "
                               f"http://127.0.0.1:{cfg.get('tunnel_local_port', 8000)}",
                     font=ctk.CTkFont(*FONT_MONO), text_color=C["muted"]).pack(side="left", padx=4)
        self._toast_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(*FONT_UI),
                                       text_color=C["ok"], anchor="e")
        self._toast_lbl.pack(side="right", padx=20)

    # ── Pestañas ──

    def _build_tabs(self):
        self._tabs = ctk.CTkTabview(self, fg_color="#141f2e", segmented_button_fg_color=C["card"])
        self._tabs.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        for name in ("Dashboard", "Túnel", "Backend", "Sincronización", "Backups",
                     "Configuración", "Logs", "Diagnóstico"):
            self._tabs.add(name)
        self.dashboard = DashboardView(self._tabs.tab("Dashboard"), self)
        self.tunnel_view = TunnelView(self._tabs.tab("Túnel"), self)
        self.backend_view = BackendView(self._tabs.tab("Backend"), self)
        self.sync_view = SyncView(self._tabs.tab("Sincronización"), self)
        self.backups_view = BackupsView(self._tabs.tab("Backups"), self)
        self.settings_view = SettingsView(self._tabs.tab("Configuración"), self)
        self.logs_view = LogsView(self._tabs.tab("Logs"), self)
        self.diagnostics = DiagnosticsView(self._tabs.tab("Diagnóstico"), self)

    # ── Eventos del servicio de sync ──

    def _on_sync_event(self, kind: str, payload):
        if kind == "log":
            msg, level = payload
            self._q.put(("sync", msg, level))
        elif kind == "result":
            self._q.put(("sync_result", payload))
        elif kind == "state":
            self._q.put(("sync_state", payload))
        elif kind == "state_error":
            self._q.put(("sync_error", payload))

    # ── Loop principal ──

    def post(self, fn) -> None:
        """Ejecuta `fn` en el hilo principal de forma segura.

        `app.after()` desde un hilo de trabajo no es thread-safe (en modo
        headless/CI lanza "main thread is not in main loop"). Aquí se enruta
        por la cola y el bucle principal lo ejecuta.
        """
        if threading.current_thread() is threading.main_thread():
            fn()
        else:
            self._q.put(("call", fn))

    def _poll(self):
        if getattr(self, "_destroyed", False):
            return
        self._tick = getattr(self, "_tick", 0) + 1
        try:
            while True:
                item = self._q.get_nowait()
                self._dispatch(item)
        except queue.Empty:
            pass
        # Refresco periódico de estado (cada ~10 s).
        if self._tick % 40 == 0:
            try:
                self.refresh_views()
            except Exception:  # noqa: BLE001 — la ventana puede estar cerrándose
                pass
        self.after(250, self._poll)

    def _dispatch(self, item):
        if item[0] == "call":
            item[1]()
            return
        kind = item[0]
        if kind == "tunnel":
            self.dashboard.append(item[1], "info")
            if "terminado" in item[1] or "finalizado" in item[1]:
                self.refresh_views()
        elif kind == "backend":
            self.dashboard.append(item[1], "info")
            self.backend_view.append(item[1], "info")
        elif kind == "sync":
            self.sync_view.append(item[1], item[2])
        elif kind == "backup":
            self.backups_view.append(item[1], item[2])
        elif kind == "sync_result":
            self.sync_view.set_busy(False)
            if item[1]:
                result = item[1]
                status = result.get("status", "?")
                color = {"ok": C["ok"], "partial": C["warn"]}.get(status, C["err"])
                self.sync_view.append(
                    f"Resultado: {status} | filas: {result.get('total_rows', 0)} "
                    f"| duración: {result.get('duration_s', 0)}s", color if status != "ok" else "ok")
                self.toast(f"Sync: {status}", "ok" if status == "ok" else "err")
            else:
                self.sync_view.append("Sync terminó con error.", "error")
            self.sync.refresh()
        elif kind == "sync_state":
            data = item[1]
            self.sync_view.apply_state(data)
            self.dashboard._lbl_sync.configure(
                text=f"Sync: {((data.get('state') or {}).get('last_run') or {}).get('status', '—')}",
                text_color=C["ok"] if ((data.get('state') or {}).get('last_run') or {}).get('status') == "ok" else C["muted"])
        elif kind == "sync_error":
            self.sync_view.append(f"Error leyendo estado: {item[1]}", "error")

    def refresh_views(self):
        self.dashboard.refresh()
        self.tunnel_view.refresh()
        self.backend_view.refresh()
        self.dashboard._lbl_sync.configure(text="Sync: —")

    def toast(self, msg: str, level: str = "info"):
        color = {"ok": C["ok"], "err": C["err"], "warn": C["warn"]}.get(level, C["info"])
        if self._toast_lbl:
            self._toast_lbl.configure(text=msg, text_color=color)
            self.after(8000, self._clear_toast)

    def _clear_toast(self):
        if not getattr(self, "_destroyed", False) and self._toast_lbl:
            self._toast_lbl.configure(text="")

    def _on_close(self):
        self._destroyed = True
        self.tunnel.terminate()
        self.backend.terminate()
        self.destroy()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ensure_dirs()

    # Modo headless para Task Scheduler / CLI (Meshweave.exe sync run).
    if argv and argv[0] in ("sync", "backup"):
        from meshweave.workers import sync_worker
        return sync_worker.main(argv[1:])
    if argv and argv[0] in ("check", "run", "status", "install", "uninstall",
                            "backup-install", "backup-uninstall", "alert-test",
                            "summary-test"):
        from meshweave.workers import sync_worker
        return sync_worker.main(argv)

    app = App()
    # Asistente de primera configuración (solo si la config está vacía y no
    # se desactiva explícitamente, p.ej. CI con MESHWEAVE_SKIP_WIZARD=1).
    if not os.environ.get("MESHWEAVE_SKIP_WIZARD") and is_first_run():
        from meshweave.ui.wizard import run_first_run_wizard
        if run_first_run_wizard(app):
            app.sync.refresh()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
