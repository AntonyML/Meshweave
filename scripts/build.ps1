# build.ps1 — Empaquetado de Meshweave
# Requiere: Python 3.11+, pyinstaller, Inno Setup (iscc en PATH o ISCC env).
#
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-Version 0.1.0]
#
# Produce:
#   dist\Meshweave.exe              (ejecutable sin consola)
#   dist\installer\Meshweave-Setup-x64.exe
#   dist\Meshweave-portable-x64.zip
#   dist\SHA256SUMS.txt

param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== 1/5 Preparando entorno de build ==" -ForegroundColor Cyan
python -m pip install -q --disable-pip-version-check pyinstaller pyinstaller-hooks-contrib

Write-Host "== 2/5 Validación (compileall + pytest) ==" -ForegroundColor Cyan
python -m compileall -q src
python -m pip install -q pytest
python -m pytest tests -q

Write-Host "== 3/5 PyInstaller ==" -ForegroundColor Cyan
python -m PyInstaller --noconfirm --clean scripts\meshweave.spec
if (-not (Test-Path "dist\Meshweave.exe")) { throw "No se generó dist\Meshweave.exe" }

Write-Host "== 4/5 Instalador Inno Setup ==" -ForegroundColor Cyan
$Iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $Iscc) { $Iscc = Get-Command (Join-Path $env:ProgramFiles(x86) "Inno Setup 6\ISCC.exe") -ErrorAction SilentlyContinue }
if ($Iscc) {
    & $Iscc.Source scripts\Meshweave.iss
} else {
    Write-Warning "Inno Setup no encontrado — se omite el instalador."
}

Write-Host "== 5/5 ZIP portable + checksums ==" -ForegroundColor Cyan
$Portable = "dist\Meshweave-portable-x64.zip"
if (Test-Path $Portable) { Remove-Item $Portable }
Compress-Archive -Path "dist\Meshweave.exe", "config.example.json", "README.md" -DestinationPath $Portable -Force

# Verificación de inicio en modo smoke (headless).
Write-Host "== Smoke test del ejecutable ==" -ForegroundColor Cyan
$env:MESHWEAVE_DATA_DIR = Join-Path $env:TEMP "meshweave-smoke-build"
& "dist\Meshweave.exe" sync status | Out-Null

# Checksums
$files = @("dist\Meshweave.exe", "dist\Meshweave-portable-x64.zip")
if (Test-Path "dist\installer\Meshweave-Setup-x64.exe") {
    $files += "dist\installer\Meshweave-Setup-x64.exe"
}
"$($files | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash.ToLower() + "  " + (Split-Path $_ -Leaf) })" | Out-File -Encoding ascii dist\SHA256SUMS.txt
Write-Host "Build completo. Artefactos en dist\ (ver SHA256SUMS.txt)" -ForegroundColor Green
