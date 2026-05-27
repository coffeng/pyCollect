param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [string]$ExePath = "",

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

function Get-SimulatorSpeed {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath
    )

    $defaultSpeed = 20.0
    $configCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'pyCollect\pycollect_gui_config.json'),
        (Join-Path $RootPath 'pycollect_gui_config.json')
    )

    foreach ($configPath in $configCandidates) {
        if (-not (Test-Path $configPath)) {
            continue
        }

        try {
            $config = Get-Content $configPath -Raw | ConvertFrom-Json
            $speed = $config.ui.simulator.speed_multiplier
            if ($null -eq $speed) {
                continue
            }

            $parsed = [double]$speed
            return [Math]::Max(0.05, [Math]::Min(1000.0, $parsed))
        }
        catch {
            continue
        }
    }

    return $defaultSpeed
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        (
            $_.Name -ieq 'python.exe' -or
            $_.Name -ieq 'pyCollect.exe'
        ) -and (
            $_.CommandLine -like '*drc_monitor_simulator.py*' -or
            $_.CommandLine -like '*pycollect.py*--qt-gui*' -or
            $_.CommandLine -like '*pyCollect.exe*--qt-gui*'
        )
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$simSpeed = Get-SimulatorSpeed -RootPath $Root

$simArgs = @(
    '-u',
    'code\drc_monitor_simulator.py',
    '--drc', ('"{0}"' -f $Drc),
    '--port', $SimPort,
    '--baud', '115200',
    '--no-rtscts',
    '--speed', ([string]$simSpeed),
    '--max-records', '0',
    '--interval', '0.02',
    '--loop',
    '--simulation-mode',
    '--control-port', $SimCtrlPort
)

$simStdOut = Join-Path $Root 'output\simulator_option3.stdout.log'
$simStdErr = Join-Path $Root 'output\simulator_option3.stderr.log'
Remove-Item $simStdOut,$simStdErr -Force -ErrorAction SilentlyContinue

$sim = Start-Process -FilePath $PythonExe -ArgumentList $simArgs -PassThru -WorkingDirectory $Root -RedirectStandardOutput $simStdOut -RedirectStandardError $simStdErr

try {
    if ($ExePath -and (Test-Path $ExePath)) {
        $exeArgs = @(
            '--qt-gui', $GuiPort,
            '--baud', '115200',
            '--no-rtscts',
            '--output', 'output\record.drc',
            '--simulation-mode',
            '--debug-stdout',
            '--control-port', $GuiCtrlPort
        )
        $gui = Start-Process -FilePath $ExePath -ArgumentList $exeArgs -PassThru -WorkingDirectory $Root
        Wait-Process -Id $gui.Id
    }
    else {
        & $PythonExe code\pycollect.py --qt-gui $GuiPort --baud 115200 --no-rtscts --output output\record.drc --simulation-mode --debug-stdout --control-port $GuiCtrlPort
    }
}
finally {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'send_control.ps1') -Target sim -Command stop | Out-Null
    }
    catch {
        # Best effort only.
    }
    if ($sim -and (Get-Process -Id $sim.Id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $sim.Id -Force -ErrorAction SilentlyContinue
    }
}
