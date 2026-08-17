# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Meshweave.exe (GUI sin consola).

Uso: pyinstaller --noconfirm scripts/meshweave.spec

Los paths se resuelven de forma ABSOLUTA respecto al directorio del spec
(PyInstaller interpreta las rutas del script como relativas a él, no al repo).
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Directorio raíz del proyecto = padre del directorio donde vive el spec.
ROOT = Path(SPECPATH).resolve().parent

hiddenimports = collect_submodules("meshweave") + [
    "meshweave.workers.sync_worker",  # modo headless (import diferido)
    "psycopg",
    "psycopg.binary",
    "psycopg.rows",
    "psycopg.pq",
    "psycopg.types.json",
    "psycopg.types.datetime",
]

datas = collect_data_files("customtkinter") + [
    (str(ROOT / "assets"), "assets"),  # icono de la ventana (iconbitmap)
]

# Recurso de versión de Windows (propiedades del exe). Lo genera
# scripts/build.ps1 → scripts/make_version_info.py; opcional fuera del build.
_version_info = ROOT / "build" / "version_info.txt"
_version = str(_version_info) if _version_info.exists() else None

a = Analysis(
    [str(ROOT / "src" / "meshweave" / "app.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Meshweave",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI sin consola (el CLI headless funciona igual)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "meshweave.ico"),
    version=_version,
)
