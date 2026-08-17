"""Genera build/version_info.txt — recurso de versión de Windows del exe.

PyInstaller lo usa con `version=` en el EXE para que el explorador y el
instalador muestren la versión real (propiedades del archivo).

Uso:  python scripts\\make_version_info.py 1.2.3
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "version_info.txt"


def _parts(version: str) -> tuple[int, int, int, int]:
    core = version.split("+", 1)[0].split("-", 1)[0]
    nums = [int(p) if p.isdigit() else 0 for p in core.split(".")]
    nums = (nums + [0, 0, 0, 0])[:4]
    return nums[0], nums[1], nums[2], nums[3]


def render(version: str) -> str:
    major, minor, build, rev = _parts(version)
    file_ver = f"{major}.{minor}.{build}.{rev}"
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {build}, {rev}),
    prodvers=({major}, {minor}, {build}, {rev}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [StringStruct('CompanyName', 'Meshweave'),
           StringStruct('FileDescription', 'Meshweave — centro de control local'),
           StringStruct('FileVersion', '{file_ver}'),
           StringStruct('InternalName', 'Meshweave'),
           StringStruct('OriginalFilename', 'Meshweave.exe'),
           StringStruct('ProductName', 'Meshweave'),
           StringStruct('ProductVersion', '{file_ver}')])
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts\\make_version_info.py <versión>", file=sys.stderr)
        return 2
    version = sys.argv[1].strip().lstrip("v")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(version), encoding="utf-8")
    print(f"version_info.txt generado: {OUT} (v{version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
