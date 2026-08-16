"""CLI del worker de Meshweave (sync + backup + tareas + alertas).

Uso:
    python -m meshweave.workers.sync_worker check           # conexiones local + nube
    python -m meshweave.workers.sync_worker run             # sync incremental ahora
    python -m meshweave.workers.sync_worker run --dry-run   # solo lee, no escribe
    python -m meshweave.workers.sync_worker status          # último run + tareas + watermarks
    python -m meshweave.workers.sync_worker install         # tarea diaria (01:00)
    python -m meshweave.workers.sync_worker uninstall
    python -m meshweave.workers.sync_worker backup          # backup del dump ahora
    python -m meshweave.workers.sync_worker backup-install  # tarea 01:30
    python -m meshweave.workers.sync_worker backup-uninstall
    python -m meshweave.workers.sync_worker alert-test      # email de prueba (Resend)
    python -m meshweave.workers.sync_worker summary-test    # prueba del resumen diario

Task Scheduler ejecuta `-m meshweave.workers.sync_worker run` (o `backup`).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from meshweave import __version__
from meshweave import sync as sync_mod
from meshweave import windows_tasks
from meshweave.config import migrate_legacy, load_config, load_state


# ── Logging ─────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    from meshweave.logging_setup import setup_logging
    setup_logging("meshweave.worker")


def emit_cli(msg: str, level: str = "info") -> None:
    """Escribe en stdout (CLI) y en el log rotativo de Meshweave."""
    line = f"{msg}"
    print(line)
    from meshweave.logging_setup import redact
    import logging
    getattr(logging.getLogger("meshweave.worker"), {
        "debug": "debug", "info": "info", "warn": "warning",
        "ok": "info", "error": "error",
    }.get(level, "info"))(redact(msg))


# ── Subcomandos ─────────────────────────────────────────────────────────────


def cmd_check(args) -> int:
    _setup_logging()
    cfg = load_config()
    res = sync_mod.check_connections(cfg)
    print("── Conexiones ──")
    ok = True
    for name, info in res.items():
        if info.get("ok"):
            print(f"  {name}: ✅ PG {info['version']} | {info['size']}")
        else:
            ok = False
            print(f"  {name}: ❌ {info.get('error', '')}")
    return 0 if ok else 1


def cmd_run(args) -> int:
    _setup_logging()
    cfg = load_config()
    emit: Callable[[str, str], None] = emit_cli if not args.dry_run else (lambda m, l: None)
    if args.dry_run:
        print("── DRY-RUN (solo lectura, no escribe en la nube) ──")
        cfg = dict(cfg)
        cfg["batch_size"] = 5  # barrido rápido de lectura
    result = sync_mod.run(cfg, emit=emit if not args.dry_run else (lambda m, l: print(m)))
    print(f"\nResultado: {result.get('status')} | filas: {result.get('total_rows')} "
          f"| tamaños: {result.get('db_sizes')}")
    if result.get("error"):
        print(f"Error: {result['error']}")
        return 1
    return 0 if result.get("status") in ("ok", "partial") else 1


def cmd_status(args) -> int:
    _setup_logging()
    cfg = load_config()
    state = load_state()
    last = state.get("last_run") or {}
    print("── Última corrida ──")
    print(f"  inicio:  {last.get('started_at', '—')}")
    print(f"  fin:     {last.get('finished_at', '—')}")
    print(f"  estado:  {last.get('status', 'sin corridas')}")
    if last.get("error"):
        print(f"  error:   {last['error']}")
    print("── Tareas ──")
    print(f"  {windows_tasks.sync_task_status(cfg)}")
    print(f"  {windows_tasks.backup_task_status(cfg)}")
    wm = state.get("watermarks", {})
    print(f"── Watermarks ({len(wm)} tablas) ──")
    for t in sorted(wm):
        w = wm[t]
        print(f"  {t:28s} {w.get('updated_at', '—') if isinstance(w, dict) else w}")
    return 0


def cmd_install(args) -> int:
    _setup_logging()
    cfg = load_config()
    ok, msg = windows_tasks.install_sync_task(cfg)
    print(msg)
    return 0 if ok else 1


def cmd_uninstall(args) -> int:
    _setup_logging()
    cfg = load_config()
    ok, msg = windows_tasks.uninstall_sync_task(cfg)
    print(msg)
    return 0 if ok else 1


def cmd_backup(args) -> int:
    _setup_logging()
    cfg = load_config()
    result = sync_mod.run_backup(cfg, emit=emit_cli)
    print(f"\nBackup: {result.get('status')} | {result.get('file', '—')} "
          f"| {(result.get('size_bytes') or 0) / 1024 / 1024:.2f} MB")
    if result.get("error"):
        print(f"Error: {result['error']}")
        return 1
    return 0 if result.get("status") == "ok" else 1


def cmd_backup_install(args) -> int:
    _setup_logging()
    cfg = load_config()
    ok, msg = windows_tasks.install_backup_task(cfg)
    print(msg)
    return 0 if ok else 1


def cmd_backup_uninstall(args) -> int:
    _setup_logging()
    cfg = load_config()
    ok, msg = windows_tasks.uninstall_backup_task(cfg)
    print(msg)
    return 0 if ok else 1


def cmd_alert_test(args) -> int:
    _setup_logging()
    cfg = load_config()
    res = sync_mod.send_test_alert(cfg)
    print(f"Alerta de prueba: {res.get('status')} | {res.get('reason') or res.get('id') or ''}")
    return 0 if res.get("status") != "error" else 1


def cmd_summary_test(args) -> int:
    _setup_logging()
    cfg = load_config()
    res = sync_mod.send_test_summary(cfg)
    print(f"Resumen de prueba: {res.get('status')} | {res.get('reason') or res.get('id') or ''}")
    return 0 if res.get("status") != "error" else 1


# ── Main ────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meshweave-sync",
        description=f"Meshweave worker (sync + backup + tareas) v{__version__}",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("check", help="prueba conexión local + nube")
    p_run = sub.add_parser("run", help="sync incremental ahora")
    p_run.add_argument("--dry-run", action="store_true", help="solo lee, no escribe")
    sub.add_parser("status", help="último run + tareas + watermarks")
    sub.add_parser("install", help="crea la tarea diaria (MeshweaveSyncService)")
    sub.add_parser("uninstall", help="elimina la tarea diaria")
    sub.add_parser("backup", help="backup del dump de la nube ahora")
    sub.add_parser("backup-install", help="crea la tarea de backup (MeshweaveBackupService)")
    sub.add_parser("backup-uninstall", help="elimina la tarea de backup")
    sub.add_parser("alert-test", help="email de prueba (Resend)")
    sub.add_parser("summary-test", help="prueba del resumen diario")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0

    # Migración única desde TunnelCloudFlare (si existe) antes de cualquier uso.
    try:
        migrated = migrate_legacy()
        if migrated:
            print("Migración única desde TunnelCloudFlare completada "
                  "(config + secretos DPAPI + historial).")
    except Exception as e:  # noqa: BLE001
        print(f"AVISO: migración legacy no aplicada: {e}")

    handlers = {
        "check": cmd_check,
        "run": cmd_run,
        "status": cmd_status,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "backup": cmd_backup,
        "backup-install": cmd_backup_install,
        "backup-uninstall": cmd_backup_uninstall,
        "alert-test": cmd_alert_test,
        "summary-test": cmd_summary_test,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
