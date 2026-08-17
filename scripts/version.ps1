# version.ps1 — Resuelve la versión de release de Meshweave.
#
# Uso:  powershell -File scripts\version.ps1 [-Version 1.2.3]
#
#   -Version "1.2.3"  → se usa tal cual (se ignora una 'v' inicial).
#   -Version "" (vacío) → automática:
#       1. Último tag git (vX.Y.Z) → bump del patch (v1.2.3 → 1.2.4).
#       2. Sin tags → 0.1.0 (versión base del proyecto).
#
# Imprime SOLO la versión (sin 'v') para poder capturarla con &.

param(
    [string]$Version = ""
)

function Get-AutoVersion {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-Warning "git no encontrado — versión automática = 0.1.0"
        return "0.1.0"
    }
    $tag = (& git describe --tags --abbrev=0 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($tag)) {
        Write-Warning "Sin tags git — versión automática = 0.1.0"
        return "0.1.0"
    }
    $v = $tag.TrimStart('v')
    if ($v -notmatch '^(\d+)\.(\d+)\.(\d+)([-+].*)?$') {
        Write-Warning "Tag «$tag» no es semver (vX.Y.Z) — versión automática = 0.1.0"
        return "0.1.0"
    }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    $patch = [int]$Matches[3]
    return "$major.$minor.$($patch + 1)"
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    Write-Output (Get-AutoVersion)
} else {
    Write-Output ($Version.Trim().TrimStart('v'))
}
