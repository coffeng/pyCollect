@echo off
setlocal

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "DRC=%ROOT%headless_test.drc"
set "SIM_PORT=COM4"
set "GUI_PORT=COM2"
set "SIM_CTRL_PORT=9031"
set "GUI_CTRL_PORT=9032"

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
echo   "%PY%" code\drc_monitor_simulator.py --drc "%DRC%" --port %SIM_PORT% --baud 115200 --no-rtscts --max-records 3600 --interval 0.02 --control-port %SIM_CTRL_PORT%
"%PY%" code\drc_monitor_simulator.py --drc "%DRC%" --port %SIM_PORT% --baud 115200 --no-rtscts --max-records 3600 --interval 0.02 --control-port %SIM_CTRL_PORT%
goto :eof

:opt2
echo [2] Qt GUI collector only
echo Command:
echo   "%PY%" code\pycollect.py --qt-gui %GUI_PORT% --baud 115200 --no-rtscts --output output\record.drc --simulation-mode --control-port %GUI_CTRL_PORT%
"%PY%" code\pycollect.py --qt-gui %GUI_PORT% --baud 115200 --no-rtscts --output output\record.drc --simulation-mode --control-port %GUI_CTRL_PORT%
goto :eof

:opt3
echo [3] Simulator loop + Qt GUI (auto-stop simulator after GUI exits)
echo Command:
echo   powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%run_option3.ps1" ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%run_option3.ps1" -PythonExe "%PY%" -Root "%ROOT:~0,-1%" -Drc "%DRC%" -SimPort "%SIM_PORT%" -GuiPort "%GUI_PORT%" -SimCtrlPort "%SIM_CTRL_PORT%" -GuiCtrlPort "%GUI_CTRL_PORT%"
goto :eof

:opt4
echo [4] Convert DRC files in output folder to CSV
echo Command:
echo   "%PY%" code\drc_2_csv.py "%ROOT%output" "%ROOT%config\params5.txt" "%ROOT%config\waves5.txt"
"%PY%" code\drc_2_csv.py "%ROOT%output" "%ROOT%config\params5.txt" "%ROOT%config\waves5.txt"
goto :eof

:opt5
echo [5] Qt GUI collector from real monitor (COM5)
echo Command:
echo   "%PY%" code\pycollect.py --qt-gui COM5 --baud 19200 --output output\record.drc --control-port %GUI_CTRL_PORT%
"%PY%" code\pycollect.py --qt-gui COM5 --baud 19200 --output output\record.drc --control-port %GUI_CTRL_PORT%
goto :eof

:opt6
echo [6] Terminal-only simulator mode (headless, JSON waveforms, prints to terminal, saves DRC)
echo Command:
echo   "%PY%" code\pycollect.py --terminal-simulator %GUI_PORT% --duration 60 --config config\pycollect_gui_config.json --output output\record.drc
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

echo   Control (from another terminal):
echo     powershell -ExecutionPolicy Bypass -File .\send_control.ps1 -Target sim -Command status
echo     powershell -ExecutionPolicy Bypass -File .\send_control.ps1 -Target sim -Command stop
echo     powershell -ExecutionPolicy Bypass -File .\send_control.ps1 -Target gui -Command stop

echo   help  Show this message
echo.
exit /b 0
