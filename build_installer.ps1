<#
.SYNOPSIS
    Build pyCollect installer via Inno Setup (ISCC).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$isccCmd = Get-Command ISCC -ErrorAction SilentlyContinue
$iscc = if ($isccCmd) { $isccCmd.Source } else { $null }
if (-not $iscc) {
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $iscc)) {
    Write-Error "Inno Setup (ISCC) not found. Install Inno Setup 6 or add ISCC to PATH."
    exit 1
}

$issFile = Join-Path $PSScriptRoot "pyCollect.iss"
if (-not (Test-Path $issFile)) {
    Write-Error "Missing installer script: $issFile"
    exit 1
}

$outputDir = Join-Path $PSScriptRoot "dist\installer"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$baseName = "pyCollect_Setup"
$outputExe = Join-Path $outputDir ($baseName + ".exe")
if (Test-Path $outputExe) {
    Remove-Item -Force $outputExe
}

Write-Host "Running Inno Setup: $iscc /O$outputDir /F$baseName $issFile"
& $iscc ("/O" + $outputDir) ("/F" + $baseName) $issFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "ISCC failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

if (-not (Test-Path $outputExe)) {
    Write-Error "Installer did not appear at expected path: $outputExe"
    exit 1
}

Write-Host "Installer built: $outputExe"
