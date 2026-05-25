@echo off
setlocal

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "DRC=C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\Example.drc"
set "SIM_PORT=COM4"
set "GUI_PORT=COM2"

if /I "%~1"=="help" goto :help
if "%~1"=="1" goto :opt1
if "%~1"=="2" goto :opt2
if "%~1"=="3" goto :opt3
if "%~1"=="4" goto :opt4
if "%~1"=="5" goto :opt5
if "%~1"=="6" goto :opt6
if "%~1"=="" goto :help

echo Unknown option: %~1
goto :help

:opt1
echo [1] Simulator only
echo Command:
echo   "%PY%" drc_monitor_simulator.py --drc "%DRC%" --port %SIM_PORT% --wait-command --max-records 3600 --interval 0.02
"%PY%" drc_monitor_simulator.py --drc "%DRC%" --port %SIM_PORT% --wait-command --max-records 3600 --interval 0.02
goto :eof

:opt2
echo [2] Qt GUI collector only
echo Command:
echo   "%PY%" pycollect.py --qt-gui %GUI_PORT% --output record.drc --simulation-mode
"%PY%" pycollect.py --qt-gui %GUI_PORT% --output record.drc --simulation-mode
goto :eof

:opt3
echo [3] Simulator loop + Qt GUI (auto-stop simulator after GUI exits)
echo Command:
echo   powershell -NoProfile -ExecutionPolicy Bypass -Command "...Start-Process simulator...; run gui; stop simulator"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$py='%PY%'; $sim = Start-Process -FilePath $py -ArgumentList 'drc_monitor_simulator.py --drc \"%DRC%\" --port %SIM_PORT% --wait-command --max-records 3600 --interval 0.02 --loop' -PassThru -WorkingDirectory '%ROOT%'; & $py pycollect.py --qt-gui %GUI_PORT% --output record.drc --simulation-mode; if (Get-Process -Id $sim.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $sim.Id -Force }"
goto :eof

:opt4
echo [4] Convert DRC files in current folder to CSV
echo Command:
echo   "%PY%" drc_2_csv.py "%ROOT%" "%ROOT%params5.txt" "%ROOT%waves5.txt"
"%PY%" drc_2_csv.py "%ROOT%" "%ROOT%params5.txt" "%ROOT%waves5.txt"
goto :eof

:opt5
echo [5] Qt GUI collector from real monitor (COM5)
echo Command:
echo   "%PY%" pycollect.py --qt-gui COM5 --output record.drc
"%PY%" pycollect.py --qt-gui COM5 --output record.drc
goto :eof

:opt6
echo [6] Terminal-only simulator mode (headless, JSON waveforms, prints to terminal, saves DRC)
echo Command:
echo   "%PY%" pycollect.py --terminal-simulator %GUI_PORT% --duration 60 --config pycollect_gui_config.json --output record.drc
"%PY%" pycollect.py --terminal-simulator %GUI_PORT% --duration 60 --config pycollect_gui_config.json --output record.drc
goto :eof

:help
echo.
echo pyCollect launcher

echo.
echo Usage:
echo   run_pycollect.bat 1
echo   run_pycollect.bat 2
echo   run_pycollect.bat 3
echo   run_pycollect.bat 4
echo   run_pycollect.bat 5
echo   run_pycollect.bat 6
echo   run_pycollect.bat help

echo.
echo Options:
echo   1  Run simulator only

echo   2  Run Qt GUI collector only
echo      (pycollect.py --qt-gui %GUI_PORT% --output record.drc --simulation-mode)

echo   3  Run simulator + Qt GUI together

echo   4  Convert DRC files in this folder to CSV

echo   5  Run Qt GUI collector from real monitor (COM5)

echo   6  Terminal-only mode: headless simulator, JSON waveforms, prints to terminal

echo   help  Show this message
echo.
exit /b 0
