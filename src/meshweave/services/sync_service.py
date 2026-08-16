"""Servicio de sync/backup para la UI (hilos + callbacks).

La interfaz NO toca psycopg ni configs directamente: llama a este servicio,
que le devuelve estados/eventos por callback.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from meshweave import sync as sync_mod
from meshweave import windows_tasks
from meshweave.config import load_config, load_state

EmitFn = Callable[[str, str], None]


class SyncService:
    def __init__(self, on_event: Callable[[str, Any], None]):
        """on_event(tipo, payload): 'log' (msg, level), 'result' (dict)."""
        self._on_event = on_event

    # ── Corridas ────────────────────────────────────────────────────────

    def run_now(self, emit: EmitFn | None = None) -> None:
        def _go():
            try:
                cfg = load_config()
                result = sync_mod.run(cfg, emit=emit or (lambda msg, lvl: None))
                self._on_event("result", result)
            except Exception as e:  # noqa: BLE001
                self._on_event("log", (f"ERROR: {e}", "error"))
                self._on_event("result", None)

        threading.Thread(target=_go, daemon=True).start()

    def run_backup(self, emit: EmitFn | None = None) -> None:
        def _go():
            try:
                cfg = load_config()
                result = sync_mod.run_backup(cfg, emit=emit or (lambda msg, lvl: None))
                self._on_event("result", result)
            except Exception as e:  # noqa: BLE001
                self._on_event("log", (f"ERROR backup: {e}", "error"))
                self._on_event("result", None)

        threading.Thread(target=_go, daemon=True).start()

    # ── Estado (lecturas rápidas, en hilo para no bloquear la UI) ───────

    def refresh(self) -> None:
        def _go():
            try:
                cfg = load_config()
                state = load_state()
                runs = sync_mod.read_runs(8)
                backups = sync_mod.read_backup_runs(8)
                sync_task = windows_tasks.sync_task_status(cfg)
                backup_task = windows_tasks.backup_task_status(cfg)
                alert = sync_mod.resolve_alert_settings(cfg)
                self._on_event("state", {
                    "cfg": cfg, "state": state, "runs": runs, "backups": backups,
                    "sync_task": sync_task, "backup_task": backup_task, "alert": alert,
                })
            except Exception as e:  # noqa: BLE001
                self._on_event("state_error", str(e))

        threading.Thread(target=_go, daemon=True).start()

    # ── Tareas de Windows ───────────────────────────────────────────────

    def install_tasks(self) -> tuple[bool, str]:
        cfg = load_config()
        ok1, m1 = windows_tasks.install_sync_task(cfg)
        ok2, m2 = windows_tasks.install_backup_task(cfg)
        return ok1 and ok2, f"{m1}\n{m2}"

    def uninstall_tasks(self) -> tuple[bool, str]:
        cfg = load_config()
        ok1, m1 = windows_tasks.uninstall_sync_task(cfg)
        ok2, m2 = windows_tasks.uninstall_backup_task(cfg)
        return ok1 and ok2, f"{m1}\n{m2}"

    # ── Alertas (pruebas) ───────────────────────────────────────────────

    def test_alert(self) -> dict[str, Any]:
        return sync_mod.send_test_alert()

    def test_summary(self) -> dict[str, Any]:
        return sync_mod.send_test_summary()
