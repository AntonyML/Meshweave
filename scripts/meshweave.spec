# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Meshweave.exe (GUI sin consola).

Uso: pyinstaller --noconfirm scripts/meshweave.spec
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hiddenimports = collect_submodules("meshweave") + [
    "meshweave.workers.sync_worker",  # modo headless (import diferido)
    "psycopg",
    "psycopg.binary",
    "psycopg.rows",
    "psycopg.pq",
    "psycopg.types.json",
    "psycopg.types.datetime",
]

datas = collect_data_files("customtkinter")

a = Analysis(
    ["src/meshweave/app.py"],
    pathex=["src"],
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
)
