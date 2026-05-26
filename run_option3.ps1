param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [Parameter(Mandatory = $true)]
    [string]$Root,

    [Parameter(Mandatory = $true)]
    [string]$Drc,

    [Parameter(Mandatory = $true)]
    [string]$SimPort,

    [Parameter(Mandatory = $true)]
    [string]$GuiPort,

    [Parameter(Mandatory = $true)]
    [string]$SimCtrlPort,

    [Parameter(Mandatory = $true)]
    [string]$GuiCtrlPort
)

Get-Process python* -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*drc_monitor_simulator*' } |
    Stop-Process -Force -ErrorAction SilentlyContinue

$simArgs = @(
    '-u',
    'code\drc_monitor_simulator.py',
    '--drc', $Drc,
    '--port', $SimPort,
    '--baud', '115200',
    '--no-rtscts',
    '--speed', '1.0',
    '--max-records', '0',
    '--interval', '0.02',
    '--loop',
    '--simulation-mode',
    '--control-port', $SimCtrlPort
)

$sim = Start-Process -FilePath $PythonExe -ArgumentList $simArgs -PassThru -WorkingDirectory $Root

try {
    & $PythonExe code\pycollect.py --qt-gui $GuiPort --baud 115200 --no-rtscts --output output\record.drc --simulation-mode --debug-stdout --control-port $GuiCtrlPort
}
finally {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'send_control.ps1') -Target sim -Command stop | Out-Null
    }
    catch {
        # Best effort only.
    }
    if (Get-Process -Id $sim.Id -ErrorAction SilentlyContinue) {
        Stop-Process -Id $sim.Id -Force
    }
}
