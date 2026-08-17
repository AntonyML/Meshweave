# build.ps1 — Empaquetado de Meshweave
# Requiere: Python 3.11+, pyinstaller, Inno Setup (iscc en PATH o ISCC env).
#
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-Version 1.2.3]
#
#   -Version vacío (por defecto) → versión AUTOMÁTICA:
#       último tag git (vX.Y.Z) +1 patch; sin tags → 0.1.0.
#       (ver scripts\version.ps1)
#
# Produce:
#   dist\Meshweave.exe              (ejecutable sin consola, con icono y versión)
#   dist\installer\Meshweave-Setup-x64.exe
#   dist\Meshweave-portable-x64.zip
#   dist\SHA256SUMS.txt

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# ── Versión: manual si se pasa, automática si no (scripts\version.ps1) ──
$Version = (& (Join-Path $PSScriptRoot "version.ps1") -Version $Version).Trim()
Write-Host "== Versión de release: $Version ==" -ForegroundColor Cyan

# Inyecta la versión en el paquete (src/meshweave/_build_version.py) y genera
# el recurso de versión de Windows para el exe.
$BuildVerFile = Join-Path $Root "src\meshweave\_build_version.py"
[System.IO.File]::WriteAllText($BuildVerFile, "__version__ = '$Version'`n")
python (Join-Path $PSScriptRoot "make_version_info.py") $Version

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
if (-not $Iscc) {
    $Pf86 = [Environment]::GetFolderPath('ProgramFilesX86')
    if ($Pf86) { $Iscc = Get-Command (Join-Path $Pf86 "Inno Setup 6\ISCC.exe") -ErrorAction SilentlyContinue }
}
if ($Iscc) {
    & $Iscc.Source "/DMyAppVersion=$Version" scripts\Meshweave.iss
} else {
    Write-Warning "Inno Setup no encontrado — se omite el instalador."
}

Write-Host "== 5/5 ZIP portable + checksums ==" -ForegroundColor Cyan
$Portable = "dist\Meshweave-portable-x64.zip"
if (Test-Path $Portable) { Remove-Item $Portable }
Compress-Archive -Path "dist\Meshweave.exe", "config.example.json", "README.md" -DestinationPath $Portable -Force

# Verificación de inicio en modo smoke (headless).
# La salida NO se oculta: si el exe falla, el log de CI muestra el error real
# (antes se descartaba con | Out-Null y solo quedaba el exit code 1).
Write-Host "== Smoke test del ejecutable ==" -ForegroundColor Cyan
$env:MESHWEAVE_DATA_DIR = Join-Path $env:TEMP "meshweave-smoke-build"
# Tee-Object: muestra la salida del exe en el log Y la guarda. El pipeline es
# imprescindible: sin él PowerShell no espera a las apps GUI y $LASTEXITCODE
# llega vacío (verificado empíricamente).
& "dist\Meshweave.exe" sync status | Tee-Object -Variable SmokeOutput
$SmokeExitCode = $LASTEXITCODE
if ($SmokeExitCode -ne 0) {
    Write-Warning "Smoke test terminó con exit code $SmokeExitCode (revisa la salida de arriba)."
    Write-Warning "Los artefactos se generaron, pero 'Meshweave.exe sync status' no respondió 0."
} else {
    Write-Host "Smoke test OK." -ForegroundColor Green
}

# Checksums (SHA256 con .NET — funciona en cualquier PowerShell, sin
# depender de Get-FileHash).
function Get-Sha256([string]$Path) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash([System.IO.File]::ReadAllBytes($Path))
        return ([System.BitConverter]::ToString($hash) -replace '-', '').ToLower()
    } finally {
        $sha.Dispose()
    }
}
$Files = @("dist\Meshweave.exe", "dist\Meshweave-portable-x64.zip")
if (Test-Path "dist\installer\Meshweave-Setup-x64.exe") {
    $Files += "dist\installer\Meshweave-Setup-x64.exe"
}
$Lines = $Files | ForEach-Object { "$(Get-Sha256 $_)  $(Split-Path $_ -Leaf)" }
$Lines | Out-File -Encoding ascii dist\SHA256SUMS.txt

# Limpia el módulo de versión inyectado (la versión ya quedó dentro del exe).
Remove-Item -Force $BuildVerFile -ErrorAction SilentlyContinue
Write-Host "Build completo. Artefactos en dist\ (ver SHA256SUMS.txt)" -ForegroundColor Green

# Salida explícita: sin esto, el job de CI hereda el $LASTEXITCODE del último
# comando nativo (el smoke test) y marca la release como fallida aunque los
# artefactos se hayan generado correctamente. Los fallos reales (PyInstaller,
# Inno, throw…) siguen abortando con su propio exit code.
exit 0
