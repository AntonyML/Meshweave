"""Checklist de preparación: qué está bien, qué falta y por qué (lenguaje natural).

Al abrir Meshweave se corre este chequeo y el resultado se muestra en la
pestaña **Estado** (resumen + lista) y en un toast. Cada punto indica además
*el tipo de motivo*, para que sepas por dónde empezar:

- ``fisico``   → falta un programa/archivo en el PC (p. ej. cloudflared.exe).
- ``config``   → faltan datos por completar en la configuración.
- ``servicio`` → algo está caído o sin instalar (Docker, tarea programada…).
- ``permisos`` → requiere ejecutar la app como Administrador.
- ``disco``    → espacio en disco bajo.

Los detalles técnicos (errores exactos, SQL, etc.) siguen en los Logs; aquí
solo se explica en lenguaje natural qué pasa y qué hacer.
"""
from __future__ import annotations

import ctypes
import shutil
from dataclasses import dataclass
from typing import Any

from meshweave import windows_tasks
from meshweave.config import BACKUPS_DIR, is_first_run, load_config
from meshweave.services.cloudflared_manager import installed_version
from meshweave.sync.engine import check_connections

# Umbral de espacio libre que se considera "poco" (los backups ocupan espacio).
_DISK_WARN_GIB = 10


@dataclass
class CheckItem:
    """Un punto del checklist, explicado en lenguaje natural."""

    key: str            # identificador estable (p. ej. "cloudflared")
    label: str          # nombre corto para mostrar
    status: str         # "ok" | "warn" | "err"
    kind: str           # fisico | config | servicio | permisos | disco | opcional
    detail: str         # qué pasa / por qué (natural)
    action: str = ""    # qué hacer (natural)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 — sin privilegios o plataforma rara
        return False


def _check_admin(admin: bool | None) -> CheckItem:
    is_admin_ = is_admin() if admin is None else admin
    if is_admin_:
        return CheckItem("admin", "Permisos de administrador", "ok", "permisos",
                         "La app corre como Administrador.")
    return CheckItem(
        "admin", "Permisos de administrador", "warn", "permisos",
        "La app no se está ejecutando como Administrador.",
        "Ciérrala y ábrela con clic derecho → «Ejecutar como administrador». "
        "Hace falta para instalar el servicio del túnel y las tareas programadas.",
    )


def _check_tunnel(cfg: dict[str, Any]) -> CheckItem:
    tid = cfg.get("tunnel_id")
    host = cfg.get("tunnel_hostname")
    if tid and host:
        return CheckItem("tunnel", "Túnel Cloudflare", "ok", "config",
                         f"Túnel configurado (hostname {host}).")
    return CheckItem(
        "tunnel", "Túnel Cloudflare", "err", "config",
        "Falta el Tunnel ID o el hostname del túnel.",
        "Pégalos en la pestaña Túnel (o Configuración). El secreto del túnel "
        "se guarda cifrado, no en la config.",
    )


def _check_cloudflared() -> CheckItem:
    ver = installed_version()
    if ver:
        return CheckItem("cloudflared", "cloudflared", "ok", "fisico",
                         f"cloudflared instalado (versión {ver}).")
    return CheckItem(
        "cloudflared", "cloudflared", "err", "fisico",
        "Falta el programa cloudflared en este PC — es un archivo (binario) "
        "que no está instalado.",
        "Descárgalo desde la pestaña Diagnóstico → «Descargar cloudflared». "
        "Se guarda en ProgramData\\Meshweave\\bin.",
    )


def _check_databases(cfg: dict[str, Any]) -> list[CheckItem]:
    items: list[CheckItem] = []
    if not cfg.get("supabase_env"):
        items.append(CheckItem(
            "db_local", "Base local (Docker)", "err", "config",
            "Falta indicar la ruta del archivo .env del proyecto Supabase local.",
            "Indícala en la pestaña Configuración (supabase_env).",
        ))
        items.append(CheckItem(
            "db_cloud", "Nube Supabase", "err", "config",
            "Faltan los datos de conexión a la nube (pooler).",
            "Revisa host, usuario y contraseña en Configuración (los secretos "
            "van cifrados).",
        ))
        return items
    try:
        res = check_connections(cfg)
    except Exception as e:  # noqa: BLE001
        items.append(CheckItem("db_local", "Base local (Docker)", "warn", "servicio",
                               f"No se pudo comprobar la base local: {e}",
                               "Revisa que Docker esté en marcha y que el stack "
                               "de Supabase esté levantado (docker compose up -d)."))
        return items
    for name, info in res.items():
        if name == "local":
            if info.get("ok"):
                items.append(CheckItem(
                    "db_local", "Base local (Docker)", "ok", "servicio",
                    f"Base local conectada (PG {info['version']} | {info['size']})."))
            else:
                items.append(CheckItem(
                    "db_local", "Base local (Docker)", "warn", "servicio",
                    "No se pudo conectar a la base local (Docker).",
                    "Comprueba que Docker esté en marcha y que el stack de "
                    "Supabase esté levantado (docker compose up -d)."))
        else:
            if info.get("ok"):
                items.append(CheckItem(
                    "db_cloud", "Nube Supabase", "ok", "servicio",
                    f"Nube conectada (PG {info['version']} | {info['size']})."))
            else:
                items.append(CheckItem(
                    "db_cloud", "Nube Supabase", "warn", "config",
                    "No se pudo conectar a la nube (pooler) de Supabase.",
                    "Revisa host, usuario y contraseña en Configuración "
                    "(los secretos van cifrados)."))
    return items


def _check_task(key: str, label: str, hora: str, status_text: str) -> CheckItem:
    if "NO INSTALADA" in status_text:
        return CheckItem(
            key, label, "warn", "servicio",
            f"No está creada la tarea que se ejecuta cada día a las {hora}.",
            "Pestaña Sincronización → «Instalar tareas».",
        )
    if "no consultable" in status_text or "desconocido" in status_text:
        return CheckItem(
            key, label, "warn", "servicio",
            f"No se pudo consultar el estado de la tarea ({hora}).",
            "Reintenta desde la pestaña Sincronización.",
        )
    return CheckItem(key, label, "ok", "servicio",
                     f"Tarea programada activa ({status_text.split(': ', 1)[-1]}, {hora}).")


def _check_alerts(cfg: dict[str, Any]) -> CheckItem:
    from meshweave.sync.alerts import resolve_alert_settings

    if resolve_alert_settings(cfg):
        return CheckItem("alerts", "Alertas por email", "ok", "config",
                         "Emails de alerta configurados (Resend).")
    return CheckItem(
        "alerts", "Alertas por email", "warn", "config",
        "Faltan los datos del email de alertas (Resend) o el destinatario.",
        "Configúralos en la sección Configuración para recibir un aviso si el "
        "sync o el backup fallan.",
    )


def _check_backend(cfg: dict[str, Any], backend_running: bool | None) -> CheckItem | None:
    if not cfg.get("backend_project_dir"):
        return None  # opcional: no configurado no es un problema
    if backend_running is False:
        return CheckItem(
            "backend", "Backend", "warn", "servicio",
            "El backend está configurado pero no está corriendo.",
            "Inícialo desde la pestaña Backend.",
        )
    return CheckItem("backend", "Backend", "ok", "servicio",
                     "Backend configurado.")


def _check_disk() -> CheckItem:
    try:
        drive = BACKUPS_DIR.anchor or "C:\\"
        total, used, free = shutil.disk_usage(drive)
        free_gib = free / 1024 ** 3
        drive_label = drive.rstrip("\\")
        label = f"Disco ({drive_label})"
        if free_gib < _DISK_WARN_GIB:
            return CheckItem(
                "disk", label, "warn", "disco",
                f"Quedan solo {free_gib:.1f} GB libres en {drive} — los backups "
                "ocupan espacio.",
                "Libera espacio o sube la retención de backups en Configuración.",
            )
        return CheckItem("disk", label, "ok", "disco",
                         f"Disco con espacio ({(free / 1024 ** 3):.1f} GB libres en {drive}).")
    except Exception:  # noqa: BLE001 — disco no comprobable
        return CheckItem("disk", "Disco", "warn", "disco",
                         "No se pudo comprobar el espacio en disco.")


def check_readiness(
    cfg: dict[str, Any] | None = None,
    *,
    backend_running: bool | None = None,
    admin: bool | None = None,
) -> list[CheckItem]:
    """Corre el checklist completo. Devuelve la lista de puntos ordenada.

    ``backend_running`` / ``admin`` son opcionales: si no se pasan, se
    comprueban solos (la UI puede pasar el estado del backend que ya conoce).
    """
    cfg = cfg or load_config()
    items = [_check_admin(admin)]
    if is_first_run(cfg):
        items.append(CheckItem(
            "first_run", "Primera configuración", "err", "config",
            "La configuración está vacía: todavía no se completó el asistente inicial.",
            "Completa el asistente de primera configuración o rellena la "
            "pestaña Configuración.",
        ))
        return items
    items.append(_check_tunnel(cfg))
    items.append(_check_cloudflared())
    items.extend(_check_databases(cfg))
    items.append(_check_task("task_sync", "Tarea de sincronización", "01:00",
                             windows_tasks.sync_task_status(cfg)))
    items.append(_check_task("task_backup", "Tarea de backup", "01:30",
                             windows_tasks.backup_task_status(cfg)))
    items.append(_check_alerts(cfg))
    backend = _check_backend(cfg, backend_running)
    if backend is not None:
        items.append(backend)
    items.append(_check_disk())
    return items


def summary(items: list[CheckItem]) -> tuple[int, int, int]:
    """(err, warn, ok) — conteos para el resumen/toast."""
    errs = sum(1 for i in items if i.status == "err")
    warns = sum(1 for i in items if i.status == "warn")
    return errs, warns, len(items) - errs - warns
