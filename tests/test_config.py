from __future__ import annotations

import sys

import pytest

from meshweave.config import DEFAULTS, cloud_db_url, load_config, save_config
from meshweave.errors import ConfigError
from meshweave.secrets import SecretStore


def test_defaults_apply_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg["schedule_time"] == "01:00"
    assert cfg["schedule_task_name"] == "MeshweaveSyncService"
    assert cfg["backup_task_name"] == "MeshweaveBackupService"


def test_save_and_reload_atomic(tmp_path):
    p = tmp_path / "config.json"
    cfg = load_config(p)
    cfg["tunnel_hostname"] = "jobs.example.com"
    cfg["batch_size"] = 300
    save_config(cfg, p)
    again = load_config(p)
    assert again["tunnel_hostname"] == "jobs.example.com"
    assert again["batch_size"] == 300
    # Respaldo .bak existe
    assert p.with_suffix(".bak").exists()


def test_save_rejects_invalid_json(tmp_path):
    # save_config valida el payload antes de reemplazar; no hay forma de pasar
    # algo no serializable porque json.dumps falla primero.
    with pytest.raises(TypeError):
        save_config({"x": object()}, tmp_path / "config.json")


def test_cloud_url_requires_components_and_password(tmp_path):
    p = tmp_path / "config.json"
    cfg = load_config(p)
    with pytest.raises(ConfigError):
        cloud_db_url(cfg)
    cfg["cloud_db_host"] = "db.example.com"
    cfg["cloud_db_user"] = "postgres.user"
    cfg["cloud_db_port"] = 5432
    cfg["cloud_db_name"] = "postgres"
    with pytest.raises(ConfigError):
        cloud_db_url(cfg)  # falta password en DPAPI


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI es Windows-only")
def test_cloud_url_uses_dpapi_password(tmp_path):
    p = tmp_path / "config.json"
    cfg = load_config(p)
    cfg["cloud_db_host"] = "db.example.com"
    cfg["cloud_db_user"] = "postgres.user"
    cfg["cloud_db_port"] = 5432
    cfg["cloud_db_name"] = "postgres"
    SecretStore().set("cloud_db_password", "sup3r")
    url = cloud_db_url(cfg)
    assert url.startswith("postgresql://postgres.user:")
    assert "sup3r" in url and "@db.example.com:5432/postgres" in url


def test_config_never_contains_secrets(tmp_path):
    """El archivo de configuración no debe guardar passwords (van a DPAPI)."""
    p = tmp_path / "config.json"
    cfg = load_config(p)
    cfg["cloud_db_host"] = "x.example.com"
    save_config(cfg, p)
    raw = p.read_text(encoding="utf-8")
    assert "password" not in raw.lower() or '"cloud_db_password"' not in raw
    # La clave por defecto no existe en DEFAULTS:
    assert "cloud_db_password" not in DEFAULTS
