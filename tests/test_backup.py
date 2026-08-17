"""Tests de resolución de rutas de dump (restauración)."""
from __future__ import annotations

from pathlib import Path

from meshweave.config import BACKUPS_DIR
from meshweave.sync.backup import _resolve_dump_path


def test_nombre_simple_se_resuelve_en_backups():
    assert _resolve_dump_path("cloud-20260816.dump") == BACKUPS_DIR / "cloud-20260816.dump"


def test_ruta_windows_se_mantiene():
    p = Path(r"C:\ProgramData\Meshweave\backups\cloud-20260816.dump")
    assert _resolve_dump_path(str(p)) == p


def test_formato_msys_slash_c_se_normaliza():
    assert _resolve_dump_path("/c/ProgramData/x.dump") == Path(r"C:\ProgramData\x.dump")


def test_formato_backslash_c_literal_se_normaliza():
    assert _resolve_dump_path(r"\c\ProgramData\x.dump") == Path(r"C:\ProgramData\x.dump")


def test_unc_no_se_toca():
    p = Path(r"\\server\share\cloud-20260816.dump")
    assert _resolve_dump_path(str(p)) == p
