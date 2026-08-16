from __future__ import annotations

import sys

import pytest

from meshweave.secrets import SecretStore

# DPAPI es Windows-only: en otros sistemas (p.ej. CI en Linux) se saltan.
pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI solo está disponible en Windows"
)


def test_roundtrip(tmp_path):
    store = SecretStore(tmp_path / "secrets.bin")
    store.set("cloud_db_password", "s3cret!")
    assert store.get("cloud_db_password") == "s3cret!"
    assert store.has("cloud_db_password")


def test_absent_key_returns_none(tmp_path):
    store = SecretStore(tmp_path / "secrets.bin")
    assert store.get("nope") is None


def test_delete(tmp_path):
    store = SecretStore(tmp_path / "secrets.bin")
    store.set("k", "v")
    store.delete("k")
    assert store.get("k") is None


def test_file_does_not_contain_plaintext(tmp_path):
    store = SecretStore(tmp_path / "secrets.bin")
    store.set("cloud_db_password", "valor-en-claro-que-no-debe-aparecer")
    raw = (tmp_path / "secrets.bin").read_bytes()
    assert b"valor-en-claro-que-no-debe-aparecer" not in raw


def test_error_message_on_non_windows(monkeypatch):
    """En no-Windows el almacén falla con un mensaje claro, no AttributeError."""
    import meshweave.secrets as secrets_mod

    monkeypatch.setattr(secrets_mod.sys, "platform", "linux")
    with pytest.raises(Exception) as excinfo:
        secrets_mod._protect(b"x")
    assert "Windows" in str(excinfo.value)
