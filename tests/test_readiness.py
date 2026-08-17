"""Tests del checklist de preparación (meshweave.readiness)."""
from __future__ import annotations

import pytest

import meshweave.readiness as rd


@pytest.fixture(autouse=True)
def fake_checks(monkeypatch):
    """Evita conexiones reales, powershell y disco en los tests."""
    monkeypatch.setattr(rd, "is_admin", lambda: True)
    monkeypatch.setattr(rd, "is_first_run", lambda cfg=None: False)
    monkeypatch.setattr(rd, "installed_version", lambda: "2024.8.2")
    monkeypatch.setattr(rd, "check_connections", lambda cfg: {
        "local": {"ok": True, "version": "17.6", "size": "16 MB"},
        "cloud": {"ok": True, "version": "17.6", "size": "17 MB"},
    })
    monkeypatch.setattr(rd.windows_tasks, "sync_task_status", lambda cfg: "MeshweaveSyncService: Ready")
    monkeypatch.setattr(rd.windows_tasks, "backup_task_status", lambda cfg: "MeshweaveBackupService: Ready")
    monkeypatch.setattr(rd.shutil, "disk_usage", lambda path: (100, 60, 40 * 1024 ** 3))


def _cfg(**kw) -> dict:
    base = {
        "tunnel_id": "abc", "tunnel_hostname": "jobs.example.com",
        "supabase_env": r"E:\Supabase\.env",
        "cloud_db_host": "pooler.example.com", "cloud_db_user": "postgres.x",
        "resend_api_key": "k", "alerts_to_email": "a@b.c",
        "backend_project_dir": "",
        "connect_timeout_seconds": 5,
    }
    base.update(kw)
    return base


def test_todo_ok():
    items = rd.check_readiness(_cfg())
    assert all(i.status == "ok" for i in items), [i for i in items if i.status != "ok"]
    errs, warns, oks = rd.summary(items)
    assert (errs, warns) == (0, 0)
    assert oks == len(items)


def test_falta_cloudflared_es_fisico():
    rd.installed_version = lambda: None
    items = rd.check_readiness(_cfg())
    cf = next(i for i in items if i.key == "cloudflared")
    assert cf.status == "err"
    assert cf.kind == "fisico"
    assert cf.action  # siempre sugiere qué hacer


def test_sin_admin_es_permisos():
    rd.is_admin = lambda: False
    items = rd.check_readiness(_cfg())
    ad = next(i for i in items if i.key == "admin")
    assert ad.status == "warn"
    assert ad.kind == "permisos"


def test_tareas_no_instaladas():
    rd.windows_tasks.sync_task_status = lambda cfg: "MeshweaveSyncService: NO INSTALADA"
    items = rd.check_readiness(_cfg())
    t = next(i for i in items if i.key == "task_sync")
    assert t.status == "warn"
    assert "01:00" in t.detail


def test_conexion_local_caida_es_servicio():
    rd.check_connections = lambda cfg: {
        "local": {"ok": False, "error": "connection refused"},
        "cloud": {"ok": True, "version": "17.6", "size": "17 MB"},
    }
    items = rd.check_readiness(_cfg())
    local = next(i for i in items if i.key == "db_local")
    assert local.status == "warn"
    assert local.kind == "servicio"
    assert "Docker" in local.action


def test_primer_uso_acorta_el_checklist():
    rd.is_first_run = lambda cfg=None: True
    items = rd.check_readiness(_cfg())
    assert any(i.key == "first_run" for i in items)
    assert len(items) == 2  # admin + primera configuración


def test_faltan_datos_de_nube_es_config():
    items = rd.check_readiness(_cfg(supabase_env=""))
    cloud = next(i for i in items if i.key == "db_cloud")
    assert cloud.status == "err"
    assert cloud.kind == "config"
