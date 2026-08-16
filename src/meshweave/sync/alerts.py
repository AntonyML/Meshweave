"""Emails vía Resend: alertas de fallo + resumen diario (monitoreo pasivo).

- La API key se lee del `.env` del backend (configurado en
  `backend_project_dir`) si no está sobreescrita en config.json.
- Cooldowns anti-spam: 60 min por tipo de alerta, 12 h para el resumen diario.
- NUNCA se incluyen credenciales en el cuerpo del email.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meshweave.config import load_config, load_state, read_env_file, save_state

_ALERT_COOLDOWN_MIN = 60
_SUMMARY_COOLDOWN_H = 12


# ── Resolución de credenciales de Resend ────────────────────────────────────


def backend_env_path(cfg: dict[str, Any]) -> Path:
    """.env del backend (para leer RESEND_API_KEY / ADMIN_EMAIL sin duplicar)."""
    p = Path(cfg.get("backend_project_dir") or "")
    if p.is_dir():
        return p / ".env"
    return p / ".env"


def resolve_alert_settings(cfg: dict[str, Any]) -> dict[str, str] | None:
    """api_key / from / to para Resend. Prioridad: config → .env del backend.

    Devuelve None si no hay key o destinatario (alertas desactivadas).
    """
    key = (cfg.get("resend_api_key") or "").strip()
    from_email = (cfg.get("resend_from_email") or "").strip()
    to_email = (cfg.get("alerts_to_email") or "").strip()

    env: dict[str, str] = {}
    try:
        env = read_env_file(backend_env_path(cfg))
    except Exception:  # noqa: BLE001
        pass
    if not key:
        key = env.get("RESEND_API_KEY", "").strip()
    if not from_email:
        from_email = env.get("RESEND_FROM_EMAIL", "hello@tonyml.com").strip()
    if not to_email:
        to_email = env.get("ADMIN_EMAIL", "").strip()
    if not key or not to_email or not from_email:
        return None
    return {"api_key": key, "from": from_email, "to": to_email}


# ── Envío ───────────────────────────────────────────────────────────────────


def send_email(cfg: dict[str, Any], subject: str, html: str) -> dict[str, Any]:
    """Envía un email vía Resend (urllib, sin dependencias extra)."""
    settings = resolve_alert_settings(cfg)
    if not settings:
        return {"status": "skipped", "reason": "Resend no configurado (falta RESEND_API_KEY o destinatario)"}
    payload = json.dumps({
        "from": f"Meshweave <{settings['from']}>",
        "to": [settings["to"]],
        "subject": subject,
        "html": html,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
            # Resend/Cloudflare bloquea peticiones sin User-Agent (error 1010).
            "User-Agent": "meshweave/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            # Resend responde solo con {"id": "..."} en éxito; normalizamos
            # para que los logs/GUI muestren status + id de forma consistente.
            return {"status": "sent", "id": body.get("id"), "reason": f"id {body.get('id', '')}".strip()}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        return {"status": "error", "reason": f"Resend API {e.code}: {body}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": str(e)}


# ── HTML ────────────────────────────────────────────────────────────────────

def _table_row(k: str, v: Any) -> str:
    return (
        f"<tr><td style='padding:6px 12px;border:1px solid #e2e8f0;color:#475569'>{k}</td>"
        f"<td style='padding:6px 12px;border:1px solid #e2e8f0;font-family:monospace'>{v}</td></tr>"
    )


def _base_html(title: str, color: str, rows: list[str], extra: str = "") -> str:
    return (
        "<div style='font-family:Arial,sans-serif;font-size:14px;color:#0f172a'>"
        f"<h2 style='color:{color}'>{title}</h2>"
        "<table style='border-collapse:collapse;margin:12px 0'>" + "".join(rows) + "</table>"
        + extra
        + "</div>"
    )


def _alert_html(kind: str, result: dict[str, Any]) -> str:
    """HTML con el resumen de la corrida fallida + cola del log."""
    rows = []
    rows.append(_table_row("Tipo", kind))
    rows.append(_table_row("Estado", result.get("status", "?")))
    rows.append(_table_row("Inicio", result.get("started_at", "—")))
    rows.append(_table_row("Fin", result.get("finished_at", "—")))
    rows.append(_table_row("Duración", f"{result.get('duration_s', 0)} s"))
    if kind == "sync":
        rows.append(_table_row("Filas procesadas", result.get("total_rows", 0)))
        sizes = result.get("db_sizes") or {}
        if sizes:
            rows.append(_table_row("Tamaños DB", f"local {sizes.get('local', '—')} | nube {sizes.get('cloud', '—')}"))
    if result.get("error"):
        rows.append(_table_row("Error", result["error"]))

    err_tables = [
        (t, st) for t, st in (result.get("tables") or {}).items() if st.get("errors")
    ]
    if err_tables:
        det = "<br>".join(
            f"{t}: {st.get('errors')} error(es), {st.get('rows', 0)} fila(s)" for t, st in err_tables[:15]
        )
        rows.append(_table_row("Tablas con error", det))

    tail = ""
    try:
        from meshweave.paths import logs_dir
        tail = "<br>".join(
            (logs_dir() / "meshweave.log").read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
        )
    except OSError:
        pass
    log_html = f"<pre style='font-size:11px'>{tail}</pre>" if tail else ""
    return _base_html(
        f"⚠ {kind.upper()} falló", "#dc2626", rows,
        "<p>Revisa la pestaña <b>Sync</b> de Meshweave o los logs en "
        "<code>%ProgramData%\\Meshweave\\logs\\</code>.</p>" + log_html,
    )


def _summary_html(result: dict[str, Any]) -> str:
    """Resumen del sync nocturno cuando termina OK (monitoreo pasivo)."""
    rows = []
    rows.append(_table_row("Estado", result.get("status", "?")))
    rows.append(_table_row("Inicio", result.get("started_at", "—")))
    rows.append(_table_row("Fin", result.get("finished_at", "—")))
    rows.append(_table_row("Duración", f"{result.get('duration_s', 0)} s"))
    rows.append(_table_row("Filas procesadas", result.get("total_rows", 0)))
    sizes = result.get("db_sizes") or {}
    if sizes:
        rows.append(_table_row("Tamaños DB", f"local {sizes.get('local', '—')} | nube {sizes.get('cloud', '—')}"))
    tables = result.get("tables") or {}
    top = sorted(tables.items(), key=lambda kv: kv[1].get("rows", 0), reverse=True)[:10]
    if top:
        det = "<br>".join(f"{t}: {st.get('rows', 0)} fila(s)" for t, st in top)
        rows.append(_table_row("Tablas con más filas", det))
    rows.append(_table_row("Tablas sincronizadas", len(tables)))
    try:
        next_run = load_config().get("schedule_time", "01:00")
    except Exception:  # noqa: BLE001
        next_run = "01:00"
    rows.append(_table_row("Próxima corrida", f"{next_run} (diaria)"))
    return _base_html(
        "📊 Sync nocturno: OK", "#16a34a", rows,
        "<p>Sin incidencias. Estado completo en la pestaña <b>Sync</b> de Meshweave.</p>",
    )


# ── Disparadores con cooldown ───────────────────────────────────────────────


def _cooldown_ok(state_key: str, kind: str, minutes: int) -> bool:
    state = load_state()
    last = (state.get(state_key) or {}).get(kind)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        if (datetime.now(timezone.utc) - last_dt).total_seconds() < minutes * 60:
            return False
    except ValueError:
        pass
    return True


def _touch_cooldown(state_key: str, kind: str) -> None:
    state = load_state()
    state.setdefault(state_key, {})[kind] = datetime.now(timezone.utc).isoformat()
    save_state(state)


def maybe_send_failure_alert(cfg: dict[str, Any], kind: str, result: dict[str, Any]) -> dict[str, Any] | None:
    """Alerta por email cuando sync/backup falla (con cooldown anti-spam)."""
    status = result.get("status")
    if status == "ok":
        return None
    if status == "error" and not cfg.get("alert_on_error", True):
        return None
    if status == "partial" and not cfg.get("alert_on_partial", True):
        return None

    interval_min = int(cfg.get("alert_min_interval_minutes", _ALERT_COOLDOWN_MIN))
    if not _cooldown_ok("alerts", kind, interval_min):
        return {"status": "skipped", "reason": "cooldown activo"}

    subject = f"⚠ {kind.upper()} falló — Meshweave (monitoreo)"
    res = send_email(cfg, subject, _alert_html(kind, result))
    _touch_cooldown("alerts", kind)
    return res


def maybe_send_summary(cfg: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    """Resumen diario cuando el sync termina OK (con cooldown para no spamear)."""
    if result.get("status") != "ok":
        return None  # el fallo ya lo cubre maybe_send_failure_alert
    if not cfg.get("summary_email", True):
        return None

    interval_h = float(cfg.get("summary_min_interval_hours", _SUMMARY_COOLDOWN_H))
    if not _cooldown_ok("summaries", "last", int(interval_h * 60)):
        return {"status": "skipped", "reason": "cooldown activo"}

    res = send_email(cfg, "📊 Sync nocturno: OK — resumen diario", _summary_html(result))
    _touch_cooldown("summaries", "last")
    return res


# ── Pruebas ─────────────────────────────────────────────────────────────────

def send_test_alert(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Email de prueba para validar la entrega de alertas."""
    cfg = cfg or load_config()
    html = _base_html(
        "🔔 Alerta de prueba — Meshweave", "#16a34a", [],
        "<p>Si recibes esto, las <b>alertas de fallo</b> de sync/backup funcionan.</p>"
        "<p>Se enviarán emails automáticos cuando el sync nocturno o el backup fallen.</p>",
    )
    return send_email(cfg, "🔔 Alerta de prueba — Meshweave", html)


def send_test_summary(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Email de prueba del resumen diario."""
    from meshweave.sync.engine import now_iso

    cfg = cfg or load_config()
    fake = {
        "status": "ok", "started_at": now_iso(), "finished_at": now_iso(), "duration_s": 3.4,
        "total_rows": 85, "db_sizes": {"local": "16 MB", "cloud": "17 MB"},
        "tables": {"users": {"rows": 8}, "job_postings": {"rows": 542},
                    "applications": {"rows": 7}, "rank_evaluations": {"rows": 94}},
    }
    html = _summary_html(fake).replace(
        "<h2 style='color:#16a34a'>", "<h2 style='color:#16a34a'>[PRUEBA] "
    )
    return send_email(cfg, "📊 Sync nocturno: OK — resumen (PRUEBA)", html)
