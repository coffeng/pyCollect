<#
.SYNOPSIS
    Code-sign pyCollect build artifacts with signtool.
.PARAMETER Target
    "exes"      - sign dist\pyCollect.exe and dist\pyCollect-cli.exe
    "installer" - sign pyCollect_Setup.exe
#>
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("exes", "installer")]
    [string]$Target
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$signtoolCmd = Get-Command signtool -ErrorAction SilentlyContinue
$signtool = if ($signtoolCmd) { $signtoolCmd.Source } else { $null }
if (-not $signtool) {
    # Common Windows SDK locations
    $candidates = @(
        "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
        "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe",
        "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $signtool = $c; break }
    }
}
if (-not $signtool) {
    Write-Error "signtool.exe not found. Install Windows SDK or add it to PATH."
    exit 1
}

$timestampUrl = "http://timestamp.digicert.com"

if ($Target -eq "exes") {
    $files = @(
        (Join-Path $PSScriptRoot "dist\pyCollect.exe"),
        (Join-Path $PSScriptRoot "dist\pyCollect-cli.exe")
    )
} else {
    $installerNew = Join-Path $PSScriptRoot "dist\installer\pyCollect_Setup.exe"
    $installerLegacy = Join-Path $PSScriptRoot "pyCollect_Setup.exe"
    if (Test-Path $installerNew) {
        $files = @($installerNew)
    } else {
        $files = @($installerLegacy)
    }
}

foreach ($f in $files) {
    if (-not (Test-Path $f)) {
        Write-Error "File not found: $f"
        exit 1
    }
    Write-Host "Signing: $f"
    & $signtool sign /a /tr $timestampUrl /td SHA256 /fd SHA256 $f
    if ($LASTEXITCODE -ne 0) {
        Write-Error "signtool failed for: $f"
        exit 1
    }
    Write-Host "Signed OK: $(Split-Path $f -Leaf)"
}
