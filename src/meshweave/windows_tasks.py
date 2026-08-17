"""Tareas programadas de Windows (Task Scheduler) — compartidas por CLI y GUI.

Las tareas ejecutan el worker con `python -m meshweave.workers.sync_worker`
(dev) o el ejecutable en modo headless (frozen), nunca un .bat.
"""
from __future__ import annotations

import subprocess as _sp
import sys
from pathlib import Path
from typing import Any

from meshweave import APP_NAME
from meshweave.paths import is_frozen, package_root
from meshweave.process_runner import CREATE_NO_WINDOW

_DEFAULT_TASK_NAMES = {
    "sync": "MeshweaveSyncService",
    "backup": "MeshweaveBackupService",
}
_DEFAULT_TIMES = {"sync": "01:00", "backup": "01:30"}


def _worker_command(subcmd: str) -> tuple[str, str, str]:
    """(execute, arguments, working_dir) para la tarea programada."""
    if is_frozen():
        # Meshweave.exe sync run / backup — headless sin consola.
        return str(Path(sys.executable)), f"sync {subcmd}", str(package_root())
    python = sys.executable
    return python, f"-m meshweave.workers.sync_worker {subcmd}", str(package_root())


def _ps_register(name: str, time_: str, subcmd: str) -> str:
    exe, args, workdir = _worker_command(subcmd)
    return (
        f"$action = New-ScheduledTaskAction -Execute '{exe}' "
        f"-Argument '{args}' -WorkingDirectory '{workdir}' ; "
        f"$trigger = New-ScheduledTaskTrigger -Daily -At {time_} ; "
        f"$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable "
        f"-ExecutionTimeLimit (New-TimeSpan -Minutes 120) -MultipleInstances IgnoreNew ; "
        f"Register-ScheduledTask -TaskName '{name}' -Action $action -Trigger $trigger "
        f"-Settings $settings -Force | Out-Null"
    )


def install_task(name: str, time_: str, subcmd: str = "run") -> tuple[bool, str]:
    """Crea (o reemplaza) una tarea diaria. Devuelve (ok, mensaje)."""
    ps = _ps_register(name, time_, subcmd)
    try:
        _sp.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=True, capture_output=True, text=True, timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        return True, f"Tarea '{name}' creada: diaria a las {time_} (arranca si el PC estaba apagado)."
    except Exception as e:  # noqa: BLE001
        return False, f"No se pudo crear la tarea '{name}': {e}"


def uninstall_task(name: str) -> tuple[bool, str]:
    try:
        _sp.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false"],
            check=True, capture_output=True, text=True, timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        return True, f"Tarea '{name}' eliminada."
    except Exception as e:  # noqa: BLE001
        return False, f"No se pudo eliminar la tarea '{name}': {e}"


def task_status(name: str) -> str:
    """Estado legible: 'Ready', 'Running', 'Disabled', 'NO INSTALADA'…"""
    try:
        r = _sp.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"$t = Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue ; "
             "if ($t) { $t.State } else { 'NO INSTALADA' }"],
            capture_output=True, text=True, timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        out = (r.stdout or r.stderr or "").strip()
        return f"{name}: {out or 'desconocido'}"
    except Exception as e:  # noqa: BLE001
        return f"{name}: no consultable ({e})"


# ── Helpers con nombres por defecto de Meshweave ─────────────────────────────


def install_sync_task(cfg: dict[str, Any]) -> tuple[bool, str]:
    return install_task(
        cfg.get("schedule_task_name", _DEFAULT_TASK_NAMES["sync"]),
        cfg.get("schedule_time", _DEFAULT_TIMES["sync"]),
        "run",
    )


def uninstall_sync_task(cfg: dict[str, Any]) -> tuple[bool, str]:
    return uninstall_task(cfg.get("schedule_task_name", _DEFAULT_TASK_NAMES["sync"]))


def sync_task_status(cfg: dict[str, Any]) -> str:
    return task_status(cfg.get("schedule_task_name", _DEFAULT_TASK_NAMES["sync"]))


def install_backup_task(cfg: dict[str, Any]) -> tuple[bool, str]:
    return install_task(
        cfg.get("backup_task_name", _DEFAULT_TASK_NAMES["backup"]),
        cfg.get("backup_time", _DEFAULT_TIMES["backup"]),
        "backup",
    )


def uninstall_backup_task(cfg: dict[str, Any]) -> tuple[bool, str]:
    return uninstall_task(cfg.get("backup_task_name", _DEFAULT_TASK_NAMES["backup"]))


def backup_task_status(cfg: dict[str, Any]) -> str:
    return task_status(cfg.get("backup_task_name", _DEFAULT_TASK_NAMES["backup"]))


def app_title() -> str:
    return APP_NAME
