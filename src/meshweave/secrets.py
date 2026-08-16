"""Almacén de credenciales cifrado con DPAPI de Windows.

Los secretos (password de la DB nube, TunnelSecret de Cloudflare, API keys)
NUNCA se guardan en JSON de configuración ni en el repo: viven en
%ProgramData%\\Meshweave\\secrets.bin, cifrados con CryptProtectData
(DPAPI), de modo que solo la cuenta de Windows que los escribió puede leerlos.

Formato: JSON {"version": 1, "entries": {clave: base64(blob_dpapi)}}.
Escritura atómica (temp + os.replace).
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path

from meshweave.errors import SecretsError
from meshweave.paths import secrets_path

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _require_windows() -> None:
    if not sys.platform.startswith("win"):
        raise SecretsError(
            "DPAPI (Windows Credential Protection) solo está disponible en Windows."
        )


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _protect(data: bytes) -> bytes:
    _require_windows()
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise SecretsError(f"CryptProtectData falló (código {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    _require_windows()
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise SecretsError(f"CryptUnprotectData falló (código {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


class SecretStore:
    """Almacén DPAPI por clave (get/set/delete/has). Thread-safe por proceso."""

    def __init__(self, path: Path | None = None):
        self.path = path or secrets_path()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_bytes()
            data = json.loads(raw.decode("utf-8"))
            return data.get("entries", {})
        except (OSError, ValueError):
            return {}

    def _save(self, entries: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": 1, "entries": entries}).encode("utf-8")
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, self.path)

    def get(self, key: str) -> str | None:
        blob = self._load().get(key)
        if not blob:
            return None
        try:
            return _unprotect(base64.b64decode(blob)).decode("utf-8")
        except SecretsError:
            # Blob ilegible (p.ej. usuario distinto): tratar como ausente.
            return None

    def set(self, key: str, value: str) -> None:
        entries = self._load()
        entries[key] = base64.b64encode(_protect(value.encode("utf-8"))).decode("ascii")
        self._save(entries)

    def delete(self, key: str) -> None:
        entries = self._load()
        if key in entries:
            del entries[key]
            self._save(entries)

    def has(self, key: str) -> bool:
        return key in self._load()

    def keys(self) -> list[str]:
        return sorted(self._load())


def get_secret(key: str) -> str | None:
    """Acceso rápido sin instanciar."""
    return SecretStore().get(key)


def set_secret(key: str, value: str) -> None:
    SecretStore().set(key, value)
