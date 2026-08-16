"""API pública del subsistema de sync (motor + alertas + backup)."""
from __future__ import annotations

from typing import Any, Callable

from meshweave.config import RUNS_LOG, load_config, load_state
from meshweave.sync.alerts import (
    maybe_send_failure_alert,
    maybe_send_summary,
    resolve_alert_settings,
    send_email,
    send_test_alert,
    send_test_summary,
)
from meshweave.sync.backup import read_backup_runs, run_backup
from meshweave.sync.engine import SyncEngine, build_local_url, check_connections

__all__ = [
    "SyncEngine", "build_local_url", "check_connections",
    "run_backup", "read_backup_runs",
    "resolve_alert_settings", "send_email", "send_test_alert", "send_test_summary",
    "maybe_send_failure_alert", "maybe_send_summary",
    "run", "read_runs", "load_config", "load_state",
]


def run(cfg: dict[str, Any] | None = None, emit: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    return SyncEngine(cfg, emit=emit).run()


def read_runs(limit: int = 8) -> list[dict[str, Any]]:
    """Últimas corridas desde logs/sync_runs.jsonl (una por línea)."""
    if not RUNS_LOG.exists():
        return []
    try:
        lines = RUNS_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(__import__("json").loads(ln))
        except ValueError:
            continue
    return out
