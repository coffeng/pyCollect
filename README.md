# pyCollect: Plan for a PyQt5 GEHC Monitor Collection Package

This document started as a plan and now also tracks implemented/tested status for the current prototype.

## Update: 2026-05-26

Today the simulator and Qt GUI integration was tightened up for the serial-loop
workflow used in option 3.

- Added localhost control servers so the simulator and GUI can be queried and
  stopped cleanly from PowerShell or other local scripts.
- Added dedicated option-3 launcher flow on Windows via `run_option3.ps1`.
- Consolidated Windows launching into `run_pycollect.bat` with
  `PYCOLLECT_RUNTIME=python|exe` for options 2/3/5, removing the separate
  EXE-only launcher scripts.
- Updated simulation mode so the simulator sends the DRC data as-is instead of
  filtering outgoing waveforms to match the current GUI request set.
- Updated simulation-mode waveform catalog colors in the GUI:
  - green = selected and currently receiving data
  - blue = currently receiving data but not selected
  - yellow/orange = selected but waiting for data
- Updated the top waveform header in simulation mode so it lists waveforms that
  are actually present in incoming packets, not merely waveforms selected in the
  GUI.
- Verified that simulation-mode catalog buttons can be unselected during active
  capture and that `Paw` appears in the live header when it is present in the
  incoming simulator stream.

### Localhost Control Ports

- Simulator control server: `127.0.0.1:9031`
- GUI control server: `127.0.0.1:9032`
- Supported commands: `ping`, `status`, `stop`

PowerShell helper:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\send_control.ps1 -Target sim -Command status
powershell -NoProfile -ExecutionPolicy Bypass -File .\send_control.ps1 -Target gui -Command stop
```

### Option 3 Notes

- `run_pycollect.bat 3` now uses `run_option3.ps1`.
- `run_option3.ps1` supports both Python and EXE collector launches.
- The simulator is started with `--simulation-mode`, `--no-rtscts`, and
  `--max-records 0` so each loop completes the entire DRC file before
  restarting.
- Verified on the current setup that option 3 receives clean packages and that
  the GUI header reports `ECG1, P1, Paw, Flow` when those waveforms are present
  in the simulator stream.

## Goal

Create a Python package and desktop application that:

1. Reads GEHC patient monitor data from serial port.
2. Stores captured data as DRC files.
3. Converts DRC to CSV (and supports CSV-to-DRC where needed).
4. Provides a PyQt5 UI with workflow quality similar to PCS Annotation Tool (clear panels, guided workflow, persistent state, robust validation).
5. Replaces the old LabVIEW iCollect workflow with a maintainable Python/PyQt5 equivalent.
6. Uploads the completed recording file automatically to the Synology Server Staging folder at 10.xx.xx.xx when recording ends.
7. Produces a Windows executable build and setup installer using similar packaging technology as ActivityLogger.

## Source Inputs to Reuse

### UI/UX Reference

- Source: `C:\Users\100014430\Documents\GitHub\Enterprise\PCS_AnnotationTool\README.md`
- Reuse conceptually:
  - Panel-based workflow with explicit steps.
  - Strong user guidance and status feedback.
  - Session state persistence and resume behavior.
  - Predictable navigation and clear actions.

### Existing iCollect Python Scripts to Copy Into This Repo

- Source folder: `C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\Python`
- Scripts identified:
  - `pycollect.py` (serial capture command sequence, DRC recording)
  - `drc_2_csv.py` (DRC parsing and CSV export)
  - `csv_2_drc.py` (CSV back to DRC)
  - `readecgdrc.py` (ECG DRC reading utilities)
  - `datasearch.py`
  - `genwave.py`
  - `tdms_2_mit.py`

### Legacy Behavior Reference

- Source document: `C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\iCollect Manual.pdf`
- Supporting legacy summary: `C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\readme.txt`
- Legacy features to preserve:
  - Serial-based data acquisition.
  - DRC recording.
  - Online and offline visualization concepts.
  - Export/conversion workflows.

### Protocol Reference (Computer Interface Spec)

- Source document: `C:\Users\100014430\Box\iCollect 5.x\Design Documentation\Software Design\M1017617_13th_S5_Computer_interface_spec.pdf`
- Purpose: GE S/5 serial computer interface protocol reference for command and payload behavior (including alarms).

#### Alarm Request Mapping Used In Code

- Protocol section: **Access to alarm information** (M1017617, chapter 5).
- Alarm request command values implemented in `code/pycollect_qt_gui.py`:
  - `DRI_AL_XMIT_STATUS = 0`
  - `DRI_AL_ENTER_DIFFMODE = 2`
  - `DRI_AL_EXIT_DIFFMODE = 3`
- Config keys supported for protocol alarm request frames:
  - `protocol.commands.alarm_xmit_status_hex`
  - `protocol.commands.alarm_enter_diffmode_hex`
  - `protocol.commands.alarm_exit_diffmode_hex`
  - Backward-compatible fallback:
    - `protocol.commands.alarm_start_hex`
    - `protocol.commands.alarm_stop_hex`

## Target Scope (What This Project Should Deliver)

1. Python package for serial capture and DRC handling.
2. PyQt5 desktop UI for capture, monitoring, and conversion tasks.
3. CLI entry points for headless operation and automation.
4. Logging, error handling, and reproducible outputs.
5. Basic test suite for packet processing and conversion correctness.
6. Optional post-recording file transfer workflow to Synology Server Staging at 100.
7. Windows distribution outputs: standalone executable and installer/setup program.

## Architecture: Python Scripts and Dependencies

### Repository Structure (All Tracked Files)

```
pyCollect/
├── README.md                              # This documentation
├── requirements.txt                       # Python dependencies
├── .gitignore                            # Git ignore rules
├── .vscode/
│   └── tasks.json                        # VS Code build/run tasks
│
├── ENTRY POINTS (Standalone Scripts)
├── pycollect.py                          # Main CLI: collection, conversion, headless modes
├── run_pycollect.bat                     # Windows batch launcher (6 options)
├── run_pycollect.sh                      # Unix/Linux launcher
│
├── SUPPORT UTILITIES (Not directly invoked by user)
├── drc_monitor_simulator.py              # Replays DRC as simulated monitor stream
├── serial_bridge.py                      # Serial port forwarding tool
├── drc_2_csv.py                          # DRC-to-CSV converter library
├── local_control.py                      # Localhost control server used by simulator and GUI
├── pycollect_qt_gui.py                   # PyQt5 GUI implementation (imported by others)
│
├── CONFIGURATION FILES
├── pycollect_gui_config.json             # JSON waveform/trend definitions (used by Qt GUI & terminal-simulator)
├── params5.txt                           # Metadata: trend channel definitions
├── waves5.txt                            # Metadata: waveform channel definitions
│
├── TEST SUITES (Smoke/Integration Tests)
├── test_pycollect_simulator_5_records.py # Unit test: pycollect library with simulator
├── ui_sidebar_smoke_test.py              # Qt GUI smoke test: sidebar widgets
├── ui_waveform_catalog_smoke_test.py     # Qt GUI smoke test: waveform catalog state machine
├── tests/serial_loopback_test.py         # Serial loopback validation for COM bridge path
├── tests/sim_gui_diag.py                 # Headless simulator-to-GUI packet diagnostic

├── CONTROL / LAUNCHER HELPERS
├── run_option3.ps1                       # Windows option-3 launcher with graceful cleanup
├── send_control.ps1                      # PowerShell client for localhost control ports
│
└── TEST DATA (Generated or Imported)
    └── (Example files, not in git; generated at runtime)
```

### Python Scripts: Purpose and Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER ENTRY POINTS                           │
├─────────────────────────────────────────────────────────────────┤
│  run_pycollect.bat (option 1-6)                                │
│      └─ Selects one of 6 collection modes                       │
│           ├─ Option 1: pycollect.py --blind                     │
│           ├─ Option 2: pycollect_qt_gui.py (PyQt5 GUI)         │
│           ├─ Option 3: pycollect.py --blind + pycollect_qt_gui │
│           ├─ Option 4: drc_2_csv.py (batch conversion)         │
│           ├─ Option 5: pycollect.py --blind --real-monitor     │
│           └─ Option 6: pycollect.py --terminal-simulator       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              CORE LIBRARY: pycollect.py                         │
│  (Protocol framing, packet parsing, DRC I/O, CLI routing)     │
├─────────────────────────────────────────────────────────────────┤
│  Main Functions:                                                │
│  ├─ main()                 → CLI argument dispatcher            │
│  ├─ blind_collect()        → Terminal-only collection          │
│  ├─ run_terminal_simulator() → Headless simulator mode (DONE)  │
│  ├─ send_hex_command()     → Serial protocol interface         │
│  ├─ process_received_data() → Unescape packets (0x7D/0x7E)    │
│  ├─ extract_first_hr_and_ecg() → Parse packet for HR/waveform │
│  ├─ build_output_filename() → Timestamp-based DRC naming      │
│  ├─ load_wave_config()     → Load JSON waveform definitions    │
│  └─ LiveMonitorPlot        → matplotlib live plotting class    │
│                                                                  │
│  Classes:                                                        │
│  └─ LiveMonitorPlot()      → Manages HR/ECG deques and plots   │
│                                                                  │
│  Imports: pyserial, matplotlib (optional), json, struct, etc    │
└─────────────────────────────────────────────────────────────────┘
         ↙                    ↓                    ↘
      ↙                      ↓                       ↘
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   SIMULATOR      │  │  Qt GUI LAYER    │  │  DRC CONVERSION  │
│  (Option 3, 6)   │  │ (Option 2, 3)    │  │  (Option 4)      │
├──────────────────┤  ├──────────────────┤  ├──────────────────┤
│drc_monitor_      │  │pycollect_qt_gui  │  │  drc_2_csv.py    │
│  simulator.py    │  │    .py           │  │                  │
│                  │  │                  │  │  Parses:         │
│ Replays DRC      │  │ • Main window    │  │  ├─ DRC packets  │
│ records as       │  │ • Sidebar        │  │  ├─ Extract data │
│ serial frames    │  │ • Waveform plot  │  │  └─ Output CSV   │
│ to COM port      │  │ • Catalog viewer │  │                  │
│                  │  │ • Status log     │  │  Imports:        │
│ Used by:         │  │                  │  │  ├─ numpy        │
│ ├─ pycollect.py  │  │ Imports:         │  │  └─ pandas       │
│ │ (--blind mode) │  │ ├─ PyQt5         │  │                  │
│ └─ Option 6      │  │ ├─ pyqtgraph     │  │ Used by:         │
│   collection     │  │ ├─ pyserial      │  │ ├─ Option 4      │
│                  │  │ ├─ pycollect     │  │ │ (batch conv.)  │
│ Config:          │  │ │ (imports)      │  │ └─ pycollect.py  │
│ └─ --drc FILE    │  │ └─ json          │  │   (future conv.) │
│ └─ --port COM#   │  │                  │  │                  │
│ └─ --max-records │  │ Config:          │  │                  │
│ └─ --interval    │  │ ├─ pycollect_    │  │                  │
│                  │  │ │ gui_config.json│  │                  │
│                  │  │ ├─ params5.txt   │  │                  │
│                  │  │ └─ waves5.txt    │  │                  │
│                  │  │                  │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Script Descriptions

#### **pycollect.py** — Core CLI and Protocol Handler
- **Purpose:** Unified entry point for all collection modes
- **Modes:**
  - `--blind` : Terminal-only collection (no GUI, no matplotlib)
  - `--gui` : matplotlib live plotting
  - `--qt-gui` : PyQt5 GUI (launches pycollect_qt_gui)
  - `--terminal-simulator` : Headless simulator mode with file-saving [DONE]
  - `--real-monitor` : Physical monitor via serial port
- **Key Functions:**
  - `blind_collect()` : Reads serial packets, prints to terminal
  - `run_terminal_simulator()` : Collects from simulator, saves DRC when `--output` given [DONE]
  - `send_hex_command()` : Sends protocol commands to serial device
  - `process_received_data()` : Unescapes 0x7D/0x7E framing
  - `extract_first_hr_and_ecg()` : Parses first HR and waveform from packet
  - `load_wave_config()` : Reads JSON to get waveform definitions
  - `build_output_filename()` : Creates timestamped DRC names
- **Dependencies:** `pyserial`, `json`, `struct`, `pathlib`
- **Optional:** `matplotlib` (for `--gui` mode only)

#### **pycollect_qt_gui.py** — PyQt5 Desktop GUI
- **Purpose:** Full-featured GUI with sidebar controls and real-time waveform display
- **Key Components:**
  - `PyCollectQtWindow` : Main window class with sidebar, log panel, plot area
  - `load_signal_config()` : Loads waveform/trend config from JSON
  - Connection panel: Port selection, baud rate, connect/disconnect buttons
  - Capture panel: Start/stop, duration/packet count spinboxes
  - Waveform catalog: Button grid with color state machine (blue/green/yellow/red)
  - Status log: Captures all operations and errors
  - Plot area: Live HR trend and ECG waveform using pyqtgraph
- **Dependencies:** `PyQt5`, `pyqtgraph`, `pyserial`, `pycollect` (imports)
- **Config Files:** `pycollect_gui_config.json`, `params5.txt`, `waves5.txt`

#### **drc_monitor_simulator.py** — Serial Monitor Emulator
- **Purpose:** Replays a DRC file as simulated serial packets for testing
- **Usage:** Runs on one COM port, feeds data while pycollect reads from paired port
- **Key Functions:**
  - Reads `.drc` file in chunks
  - Frames each chunk with 0x7E flags and 0x7D escaping
  - Transmits to COM port at controllable interval (e.g., 0.02s)
  - Supports `--wait-command` mode (pauses between records until signaled)
- **CLI Args:** `--drc FILE`, `--port COM#`, `--interval SEC`, `--max-records N`, `--wait-command`
- **Dependencies:** `pyserial`
- **Typical Use:**
  - Paired with pycollect in headless test: simulator on COM4, collector on COM2

#### **drc_2_csv.py** — DRC-to-CSV Converter
- **Purpose:** Parses DRC binary file and exports trends/waveforms to CSV
- **Key Functions:**
  - Reads DRC packet structure
  - Extracts trend data (HR, pressures, SpO2, etc.)
  - Extracts waveform samples (ECG, pressures, etc.)
  - Outputs separate CSV files for trends and waveforms
- **CLI Args:** Input folder or file path
- **Output:** `*_trends.csv`, `*_waveforms.csv` alongside input
- **Dependencies:** `numpy`, `pandas`, `struct`, `csv`
- **Supports:** Batch conversion of folders

#### **serial_bridge.py** — Serial Port Forwarder
- **Purpose:** Forwards bytes from one COM port to another
- **Use Case:** Testing multi-process scenarios, routing through virtual ports
- **CLI Args:** `--src COM#`, `--dst COM#`, `--src-baud`, `--dst-baud`
- **Dependencies:** `pyserial`

#### **test_pycollect_simulator_5_records.py** — Quick Integration Test
- **Purpose:** Runs pycollect library function against simulator for 5 records
- **Verifies:** Packet reception, HR extraction, no crashes
- **Uses:** `pycollect` module imports
- **Dependencies:** `pycollect`

#### **ui_sidebar_smoke_test.py** — Qt GUI Widget Test
- **Purpose:** Headless smoke test of all sidebar controls
- **Verifies:**
  1. Connection section: Port combo, port list refresh
  2. Display Windows: Duration/trend/waveform spinboxes
  3. Capture section: Start/stop button wiring
  4. Signal Selection: Request buttons and selector grid
  5. Status log: Append and debug stdout mirroring
- **Runs:** Qt GUI in offscreen mode (QT_QPA_PLATFORM=offscreen)
- **Exit Code:** 0 on all pass, non-zero on failure

#### **ui_waveform_catalog_smoke_test.py** — Qt GUI State Machine Test
- **Purpose:** Validates waveform catalog button color state machine
- **Tests:** Blue (fresh), Green (received), Yellow (stale), Red (error), Default (idle)
- **Methodology:** Simulates button clicks, manipulates timestamps, verifies colors
- **Runs:** Qt GUI in offscreen mode
- **Exit Code:** 0 on all pass, non-zero on failure

### Configuration Files

| File | Format | Purpose |
|------|--------|---------|
| `pycollect_gui_config.json` | JSON | Defines which trends/waveforms to collect and display in Qt GUI and terminal-simulator mode |
| `params5.txt` | Tab-sep rows | Metadata: trend channel names, units, scaling (HR, pressures, SpO2, etc.) |
| `waves5.txt` | Tab-sep rows | Metadata: waveform channel names, sampling rates (ECG @ 240 Hz, etc.) |

### Collection Flow Diagram

```
BLIND COLLECTION (Terminal-only, no GUI)
────────────────────────────────────────
  pycollect.py --blind [--output FILE.drc]
       ↓
  Open serial port (real or paired to simulator)
       ↓
  Send START command → Monitor/simulator responds
       ↓
  Loop: receive packets → unescape → extract HR/ECG → print to terminal
       ↓
  [Optional] Accumulate bytes → save to DRC file
       ↓
  STOP → Close port, show summary

TERMINAL-SIMULATOR (Headless, file-save enabled) [DONE]
────────────────────────────────────────────────────────
  pycollect.py --terminal-simulator COM2 --duration 60 --output my_recording.drc
       ↓
  Load waveform config from JSON
       ↓
  Open simulator port (expects simulator running on paired COM port)
       ↓
  Send START command
       ↓
  Loop for 60 seconds:
    ├─ Receive packet
    ├─ Unescape, parse HR/ECG
    ├─ Print formatted data to terminal
    ├─ Accumulate raw bytes
       ↓
  Time limit reached
       ↓
  Send STOP command
       ↓
  Close port, save accumulated bytes to DRC file, show summary

MATPLOTLIB GUI (Live plot, terminal fallback)
──────────────────────────────────────────────
  pycollect.py --gui --real-monitor COM1
       ↓
  Same packet loop as --blind
       ↓
  For each HR sample: append to deque, redraw line chart
       ↓
  For each ECG sample: append to deque, redraw waveform plot

PyQt5 FULL GUI
───────────────
  run_pycollect.bat [2]  or  python pycollect_qt_gui.py
       ↓
  Launch PyCollectQtWindow with sidebar
       ↓
  User selects port, waveforms, duration
       ↓
  User clicks START
       ↓
  Window spawns pycollect collection thread
       ↓
  Packets received, parsed, stored in buffers
       ↓
  Plot area updates in real-time
       ↓
  Status log appends operation messages
       ↓
  User clicks STOP or duration reached
       ↓
  DRC file saved, summary shown

BATCH DRC-to-CSV CONVERSION
────────────────────────────
  run_pycollect.bat [4]  or  python drc_2_csv.py <folder>
       ↓
  drc_2_csv.py walks folder for *.drc files
       ↓
  For each DRC:
    ├─ Parse packets
    ├─ Extract trends, waveforms
    ├─ Output *_trends.csv, *_waveforms.csv
       ↓
  Done
```

## Proposed Repository Structure

```
pyCollect/
  README.md
  pyproject.toml
  requirements.txt
  src/
    pycollect/
      __init__.py
      app.py
      config.py
      serial/
        transport.py
        protocol.py
        capture_service.py
      drc/
        writer.py
        reader.py
        converters.py
      ui/
        main_window.py
        panels/
          connection_panel.py
          capture_panel.py
          file_panel.py
          conversion_panel.py
          log_panel.py
      persistence/
        state_store.py
      cli/
        main.py
  scripts_legacy/
    iCollect_python/
      (copied scripts from source, preserved as baseline)
  tests/
    test_protocol.py
    test_drc_conversion.py
    test_state_store.py
```

## Implementation Plan (Phased)

### Phase 0: Baseline Import and Freeze

1. Copy all scripts from `...\iCollect\Python` into `scripts_legacy/iCollect_python/` unchanged.
2. Add a short inventory table documenting each script, purpose, and known limits.
3. Add sample DRC test assets (if allowed) or synthetic fixtures for tests.

Acceptance criteria:
- All source scripts exist in repo under a dedicated legacy folder.
- No functional modifications to copied scripts in this phase.

### Phase 1: Core Serial and Protocol Library

1. Extract and modularize serial communication logic from `pycollect.py`.
2. Implement protocol framing/parsing module:
   - Flag detection (0x7E).
   - Escape handling (0x7D / XOR 0x20).
   - Packet validation rules.
3. Implement capture service that writes timestamped `.drc` files.
4. Add structured logging and retry behavior for serial errors.

Acceptance criteria:
- CLI can connect to a COM port and collect data into DRC files.
- Start/stop command flow is reproducible and logged.

### Phase 2: Conversion and Data Processing Services

1. Wrap `drc_2_csv.py` functionality into importable library APIs.
2. Wrap `csv_2_drc.py` as optional reverse-conversion utility.
3. Normalize output schema and timestamp handling.
4. Add deterministic error reporting for malformed/partial DRC records.

Acceptance criteria:
- DRC-to-CSV conversion works from CLI and library call.
- Conversion results are validated against known baseline outputs.

### Phase 3: PyQt5 UI (PCS-Style Workflow)

1. Build a main window with stepwise panels:
   - Connection setup (port, baud, parity, RTS/CTS).
   - Capture controls (start, stop, duration/packet target).
   - Live status (packet count, bytes, timestamps, warnings).
   - File outputs (DRC location, naming, rotation rules).
   - Conversion actions (DRC -> CSV, optional CSV -> DRC).
2. Add status bar, actionable errors, and operation logs.
3. Keep the workflow explicit and guided, similar to PCS tool conventions.

Acceptance criteria:
- User can perform end-to-end flow in UI without terminal usage.
- UI remains responsive during capture and conversion.

### Phase 4: State Persistence and Session Resume

1. Implement persistent state file (for example `.pycollect_state.json`).
2. Persist last-used serial settings, output folder, conversion options.
3. Restore state on startup with safe fallback on invalid settings.

Acceptance criteria:
- App reopens with previous working context.
- Invalid persisted values do not crash startup.

### Phase 5: Packaging, Quality, and Release

1. Package with `pyproject.toml` and console/gui entry points.
2. Add tests for protocol parsing, packet edge cases, and conversions.
3. Add lint/type checks and a CI pipeline.
4. Produce user documentation and migration notes from LabVIEW iCollect.
5. Add configurable end-of-recording auto-upload to Synology Server Staging (100), with retry/error reporting in logs/UI.
6. Add Windows packaging pipeline matching ActivityLogger-style tooling (for example: PyInstaller for `.exe` build and Inno Setup for installer).

Acceptance criteria:
- Installable package with executable app entry point.
- Windows setup program installs/uninstalls cleanly and launches the packaged app.
- Test suite passes in CI.

## UI Design Notes (PyQt5 Equivalent of Legacy LabVIEW Intent)

1. Preserve workflow clarity over visual complexity.
2. Separate online capture and offline conversion modes clearly.
3. Show operation state at all times: connected, collecting, converting, idle.
4. Include operator-friendly safety checks before capture start.
5. Keep all destructive operations explicit and confirmable.

## Dependency Plan

Core dependencies (expected):

- `PyQt5`
- `pyserial`
- `pandas`
- `numpy`
- `pyqtgraph` (if live waveform/trend plotting is included)

Optional:

- `pytest`
- `ruff` and `mypy`

## Migration Mapping (Legacy -> New Package)

- `pycollect.py` -> `serial/transport.py`, `serial/protocol.py`, `serial/capture_service.py`, `cli/main.py`
- `drc_2_csv.py` -> `drc/reader.py`, `drc/converters.py`
- `csv_2_drc.py` -> `drc/writer.py`, `drc/converters.py`
- `readecgdrc.py` and related helpers -> `drc/reader.py` extensions

## Risks and Mitigations

1. Proprietary protocol edge cases.
   - Mitigation: golden test fixtures and packet-level regression tests.
2. Serial transport instability on different hardware.
   - Mitigation: robust reconnect logic and user-visible diagnostics.
3. Drift between legacy script outputs and new API outputs.
   - Mitigation: side-by-side baseline comparison tests.
4. UI freezing during I/O-heavy operations.
   - Mitigation: worker threads/signals for capture and conversion tasks.

## Definition of Done

Status legend: `[DONE]` implemented and tested, `[IN PROGRESS]` partially implemented, `[PENDING]` not yet verified.

1. `[IN PROGRESS]` Legacy Python scripts are copied and documented in this repository.
2. `[IN PROGRESS]` PyQt5 app performs connect -> capture -> save DRC -> convert to CSV.
3. `[IN PROGRESS]` Core parsing and conversion paths have automated tests.
4. `[DONE]` Operator can resume prior session settings safely.
5. `[IN PROGRESS]` Documentation describes migration from old LabVIEW workflow to Python.

### Done and Tested Evidence (Current)

- `[DONE]` Sidebar workflow behaviors are implemented and tested via `ui_sidebar_smoke_test.py`.
- `[DONE]` Waveform catalog request/color state machine is implemented and tested via `ui_waveform_catalog_smoke_test.py`.
- `[DONE]` Simulator short-run test harness entrypoint is implemented and runnable via `test_pycollect_simulator_5_records.py --help`.

## Serial Test Utilities (Added for Development Testing)

The repository now includes two helper scripts for testing serial collection with
the sample DRC file at:

- `C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\Example.drc`

### 1) DRC Monitor Simulator

File: `drc_monitor_simulator.py`

Purpose:
- Reads DRC records from file.
- Wraps each record as serial frame with `0x7E` flags and escaped payload bytes.
- Writes stream to a serial port to emulate a monitor.
- Replays records using DRC record timestamps (normal speed), with optional
  speed multiplier and runtime config hot reload.

Example command:

```bash
python drc_monitor_simulator.py --drc "C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\Example.drc" --port COM2 --loop --wait-command --interval 0.02
```

Speed-aware example command:

```bash
python drc_monitor_simulator.py --drc "C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\Example.drc" --port COM2 --loop --wait-command --config pycollect_gui_config.json
```

### 2) COM Bridge (Source -> Destination)

File: `serial_bridge.py`

Purpose:
- Forwards bytes from one COM port to another, for example `COM2 -> COM1`.

Example command:

```bash
python serial_bridge.py --src COM2 --dst COM1 --src-baud 115200 --dst-baud 115200
```

### Important Windows COM Note

A physical COM port is usually exclusive to one process. Because of that,
running a simulator on `COM2` and a bridge also reading `COM2` often fails.

Preferred setups:

1. Virtual null-modem pair (recommended):
  - Collector uses `COM1`
  - Simulator uses `COM2`
  - No Python bridge needed (pair handles routing)
2. Three-port setup when bridge is required:
  - Simulator writes `COM3`
  - Bridge forwards `COM3 -> COM1`
  - Collector reads `COM1`

## Headless Terminal-Only Mode (No PyQt Required)

For testing or automated scripting without a GUI, use the `--terminal-simulator` mode:

**File:** `pycollect.py`

**Purpose:**
- Runs collection in headless mode.
- Reads waveform definitions from the JSON config file.
- Extracts and prints waveform data (heart rate, ECG samples) to terminal for each package.
- **Optionally saves the DRC file** when `--output` is specified.
- Auto-stops after specified duration.
- Does NOT require PyQt5 to be installed.

**Example command (60-second run, save to file):**

```bash
python pycollect.py --terminal-simulator COM2 --duration 60 --config pycollect_gui_config.json --output my_recording.drc
```

**Example command (terminal output only, no file):**

```bash
python pycollect.py --terminal-simulator COM2 --duration 60 --config pycollect_gui_config.json
```

**Output example with file-save:**

```
Terminal simulator mode on COM2
Loaded 4 waveform definitions from config
Running for 60 seconds...

[Package 1] 2026-05-25 14:30:45 | Length: 2048 bytes
  Heart Rate (first): 72 bpm
  Waveform (first): 512 samples | min=-15, max=45, avg=12.3
    First 10: [10, 12, 8, 15, 14, 11, 9, 13, 10, 12]
    Last 10:  [11, 10, 12, 13, 9, 14, 11, 12, 10, 11]

...

============================================================
Collection stopped after 60.0s
Total packages received: 61
Data saved to my_recording.drc (48894 bytes)
============================================================
```

**Quick access from batch file:**

```batch
run_pycollect.bat 6
```

This is useful for:
- CI/CD pipelines and headless servers
- Automated tests without GUI dependencies
- Remote collection via SSH or scripted execution
- Minimal resource footprint
- Integration with tools that don't support PyQt5

## Current Prototype Features And Verifiable Requirements

This chapter captures what is currently implemented and what should be
re-verified during future regression checks.

### Enumerated Features

1. CLI capture entry point in `pycollect.py` supports blind mode, matplotlib
  mode, Qt GUI mode, and headless terminal-simulator mode.
2. DRC monitor simulator in `drc_monitor_simulator.py` replays DRC records as
  framed serial data with escape handling compatible with monitor-style
  transport (`0x7E` flag framing, `0x7D` escaping).
3. Qt GUI (`pycollect_qt_gui.py`) supports autostart capture when port is
  provided from CLI.
4. Terminal-simulator mode (`--terminal-simulator`) runs headless collection and
  prints extracted waveform data (HR, ECG samples) to terminal without PyQt5.
5. Output naming supports user-provided base name via `--output` while keeping
  timestamp suffix in saved DRC filename.
6. Trend and waveform configuration is loaded from a single JSON file
  (`pycollect_gui_config.json`).
7. Wave channel metadata (label, unit, divider, sample rate, sr_type) is
  loaded from `waves5.txt` row identifiers selected in JSON.
8. Plot labels and units are dynamic and metadata-driven; no hardcoded
  trend/wave label names are required for selected channels.
9. Signal selection sidebar section provides 8 selectable slots (4 trends,
  4 waves) in a 2x4 button grid.
10. Slot selection uses prebuilt popup tables so open-time is mostly filter
   cost, not full table construction.
11. Slot selection tables support positive-data filtering using rows observed
   with positive values during capture.
12. Wave extraction includes robust fallback by channel order when incoming
   sr_type mapping does not exactly match expected row mapping.
13. Simulator-friendly mode (`--simulation-mode`) collapses Connection and
   Capture sections on autostart.
14. Simulator-friendly mode auto-closes the GUI 10 seconds after the last
   received package.
15. Simulator supports `--speed` multiplier override and `--config` hot reload
  of `ui.simulator.speed_multiplier` from `pycollect_gui_config.json`.
16. Simulator handles serial-open failures with a clear COM port conflict hint
  instead of an unhandled traceback.
17. CLI wrapper (`pycollect.py`) forwards `--duration` and `--debug-stdout`
  to Qt GUI mode.
18. Qt GUI supports a Waveform Request Catalog section with per-row request
  toggles and state-driven button coloring (blue/green/yellow/red/default).
19. Localhost control servers support `ping`, `status`, and `stop` on
  `127.0.0.1:9031` (simulator) and `127.0.0.1:9032` (GUI).
20. Windows option 3 uses `run_option3.ps1` to launch simulator + GUI and stop
  the simulator cleanly after the GUI exits.
21. Simulation mode in `drc_monitor_simulator.py` can send the DRC stream
  without outgoing waveform filtering so the GUI can adjust wave selections
  independently.
22. Simulator loop mode can replay the full DRC file and only then restart the
  loop (`--max-records 0`).
23. In simulation mode, wave catalog buttons indicate live availability:
  green=selected+receiving, blue=receiving+not selected,
  yellow/orange=selected+waiting.
24. In simulation mode, the waveform header reports waveforms detected in
  incoming packets rather than only waveforms selected for display.
25. Displayed wave rows are protected from being unrequested only in the
  non-simulation path; simulation mode allows live deselection while capturing.
26. Qt GUI log can mirror to stdout when `--debug-stdout` is enabled.

### Enumerated Requirements For Future Verification

1. `python pycollect.py --help` must list `--output` and

---

## Planned Repository Reorganization

> **Status: PLANNED — not yet executed.**
> This section documents the agreed folder structure before any files are moved.

### Motivation

The current root folder mixes Python source, test scripts, config files, generated
output files, and log files at the same level. The reorganization separates
concerns so that each file type lives in a predictable location and the root stays
minimal.

### Proposed Folder Layout

```
pyCollect/
│
├── README.md                        ← project documentation (stays in root)
├── requirements.txt                 ← Python dependencies (stays in root)
├── .gitignore                       ← updated to reflect new paths
├── run_pycollect.bat                ← Windows launcher (stays in root; paths updated)
├── run_pycollect.sh                 ← Unix launcher (stays in root; paths updated)
│
├── code/                            ← all Python source scripts
│   ├── pycollect.py                 ← core CLI: capture, protocol, DRC I/O
│   ├── pycollect_qt_gui.py          ← PyQt5 desktop GUI
│   ├── drc_2_csv.py                 ← DRC-to-CSV converter
│   ├── drc_monitor_simulator.py     ← replays DRC as simulated serial stream
│   └── serial_bridge.py             ← serial port forwarding utility
│
├── tests/                           ← all automated tests (unit + smoke)
│   ├── test_pycollect_simulator_5_records.py
│   ├── ui_sidebar_smoke_test.py
│   ├── ui_lock_role_smoke_test.py
│   └── ui_waveform_catalog_smoke_test.py
│
├── config/                          ← static signal definitions and GUI config
│   ├── pycollect_gui_config.json    ← waveform/trend selections and UI settings
│   ├── params5.txt                  ← trend channel metadata (label, unit, divider)
│   └── waves5.txt                   ← waveform channel metadata (SR, label, unit)
│
├── input/                           ← reference and test DRC input files
│   ├── headless_test.drc            ← used for headless/terminal smoke runs
│   └── record_timeout_test.drc     ← timeout edge-case test fixture
│
└── output/                          ← generated files (gitignored)
    ├── *.drc                        ← recorded DRC files from live or simulator runs
    ├── *_trends.csv                 ← CSV exports (trend channels)
    ├── *_waves.csv                  ← CSV exports (waveform channels)
    └── *.log                        ← conversion and session log files
```

### Files That Stay in Root

| File | Reason |
|---|---|
| `README.md` | Standard project documentation entry point |
| `requirements.txt` | Tooling convention: dependency files at root |
| `.gitignore` | Git convention: must be at repo root |
| `run_pycollect.bat` | End-user launcher; discoverable at root |
| `run_pycollect.sh` | End-user launcher; discoverable at root |

### Files Removed from Root (Moved or Gitignored)

| Current file | Destination | Notes |
|---|---|---|
| `pycollect.py` | `code/` | core script |
| `pycollect_qt_gui.py` | `code/` | GUI module |
| `drc_2_csv.py` | `code/` | converter |
| `drc_monitor_simulator.py` | `code/` | simulator |
| `serial_bridge.py` | `code/` | utility |
| `ui_sidebar_smoke_test.py` | `tests/` | smoke test |
| `ui_lock_role_smoke_test.py` | `tests/` | smoke test |
| `ui_waveform_catalog_smoke_test.py` | `tests/` | smoke test |
| `test_pycollect_simulator_5_records.py` | `tests/` | integration test |
| `pycollect_gui_config.json` | `config/` | signal config |
| `params5.txt` | `config/` | channel metadata |
| `waves5.txt` | `config/` | channel metadata |
| `headless_test.drc` | `input/` | test fixture |
| `record_timeout_test.drc` | `input/` | test fixture |
| `record.drc` | `output/` (gitignored) | generated recording |
| `record_trends.csv` | `output/` (gitignored) | generated CSV |
| `record_waves.csv` | `output/` (gitignored) | generated CSV |
| `*.log` | `output/` (gitignored) | generated logs |

### Required Code Changes When Executing

1. **`run_pycollect.bat` / `run_pycollect.sh`**: update all script paths from
   e.g. `pycollect.py` → `code\pycollect.py` and default output path to
   `output\record.drc`; pass `--config config\pycollect_gui_config.json`.
2. **`code/pycollect.py`**: update default config path and any relative path
   references to `params5.txt` / `waves5.txt` to resolve from `config/`.
3. **`code/pycollect_qt_gui.py`**: same config path update; ensure `import
   pycollect` resolves (add `code/` to `sys.path` or use a `conftest.py`).
4. **`tests/`**: add a `conftest.py` (or update `sys.path` at top of each test)
   so `import pycollect_qt_gui` finds scripts in `code/` and the config in
   `config/`.
5. **`.gitignore`**: add `output/` directory contents; keep `output/.gitkeep`
   so the empty folder is tracked.
6. **Smoke test runner**: update `QT_QPA_PLATFORM=offscreen` invocations to
   run from the `tests/` folder or pass explicit paths.

  `--simulation-mode` options.
2. `python -m py_compile pycollect.py pycollect_qt_gui.py` must complete
  without errors.
3. `python pycollect.py --qt-gui COM2 --output record.drc` must save output as
  `record_YYMMDDHHMMSS.drc` after capture completion.
4. JSON config load must expose exactly 4 selected trend rows and 4 selected
  wave rows, and also expose complete available row catalogs from txt files.
5. Changing selected row identifiers in `pycollect_gui_config.json` must change
  displayed labels/units/dividers without code changes.
6. SpO2 display must use divider from its selected `params5.txt` row so values
  are rendered in percent units.
7. Pleth plot must show data in normal simulator runs with default config.
8. Signal selection popups must open quickly (no full-table rebuild on every
  click) and still honor positive-data filtering.
9. Slot reassignment (trend/wave buttons) must update plot title and y-axis
  label/unit to the newly selected row metadata.
10. If started with `--simulation-mode` and CLI autostart port, Connection and
   Capture sections must start collapsed.
11. If started with `--simulation-mode`, GUI must close automatically after
   10 seconds with no received package.
12. Running simulator + collector on configured COM bridge pair must complete
   with clean process exit and produce a non-empty DRC file.
13. `python drc_monitor_simulator.py --help` must list `--speed` and
  `--config` options.
14. With simulator `--config pycollect_gui_config.json` and loop mode,
  changing `ui.simulator.speed_multiplier` at runtime must change replay
  speed without restarting the simulator.
15. In Qt GUI, catalog button state must follow:
  blue=requested/no data yet,
  green=requested+receiving,
  red=requested+timed-out,
  yellow=not requested but receiving,
  default=not requested and stale/no data.
16. In simulation mode, wave catalog button state must follow:
  green=selected+currently receiving,
  blue=currently receiving but not selected,
  yellow/orange=selected but waiting for data,
  default=not selected and not currently receiving.
17. In simulation mode, clicking a currently displayed wave row in the catalog
  must allow deselection while capture is active.
18. In non-simulation mode, clicking a currently displayed wave row in catalog
  must keep it requested and log a protection message.
19. The simulation-mode header must list waveforms actually present in recent
  incoming packets, including unselected rows such as `Paw` when present.
20. `python pycollect.py --help` and `python pycollect_qt_gui.py --help` must
  show `--debug-stdout`; GUI log lines must be mirrored to stdout when used.



## DOC2822852 Product Requirements Traceability

The following table maps each requirement from `DOC2822852 iCollect Product Requirements Specification` to its current implementation status in this PyQt5 port.

Legend:
- ✅ Implemented (verified in this codebase)
- 🟡 Partial (basic capability present; gaps noted)
- ❌ Not implemented (missing in this codebase)
- N/A Out of scope for this port

### 5.1 Features and functions to fulfill Intended Use

#### 5.1.1 Starting up Collect

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| ~~PS_COLLECT_UI_001 / URS_001~~ | ~~Registration via password.~~ | ~~❌~~ | ~~No password / registration prompt in `pycollect_qt_gui.py`. The new **User Role** combo (Admin/Reviewer/Recorded) is a UX permission layer, not authenticated registration.~~ |
| PS_COLLECT_UI_002 | Restart reuses previous session config (paths, waveform & parameter selections) without explicit save. | ✅ | `pycollect_gui_config.json` is read at startup and written on close (`_save_runtime_config`); channel selections, baudrate, trend interval, section locks, and user role all persist. |
| ~~PS_COLLECT_UI_003 / URS_003~~ | ~~Indicate "not intended for clinical use" (research only).~~ | ~~❌~~ | ~~No on-screen disclaimer banner / startup notice currently shown in the GUI.~~ |

#### 5.1.2 OnLine Mode

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_004 / URS_004 | Collect selected trended parameters to binary DRC. | ✅ | `pycollect.py` writes DRC; trend rows configurable via `params5.txt` + JSON. |
| PS_COLLECT_UI_005 | Collect selected waveforms displayed on monitor to binary DRC. | ✅ | Dynamic waveform request frame in `CollectorWorker._build_wave_request_frame` + simulator filtering verified. |
| PS_COLLECT_UI_006 / URS_006 | Collect on-screen alarms to binary DRC. | ❌ | No alarm subrecord handling in the current collector (only trend + waveform subrecords processed). |
| PS_COLLECT_UI_007 / URS_007 | All collected trends/waveforms/alarms selectable to visualize. | 🟡 | Trends and waveforms are selectable via the sidebar catalog and 4-slot graph display; alarms are not displayed. |
| PS_COLLECT_UI_008 / URS_008 | Trend collection interval selectable from 5 sec to 1 hour. | 🟡 | New **Trend Interval** spinner in *Monitor Connection* covers 5–120 s in 5-s steps and persists to `ui.trend_interval_sec`. Upper bound 120 s instead of 3600 s — extend `setMaximum` to fully satisfy spec. |

#### 5.1.3 Notes

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_009 / URS_001(notes) | Annotations via a notes editor. | ❌ | No notes editor UI. |
| PS_COLLECT_UI_010 | Notes stored to a file. | ❌ | No notes persistence. |

#### 5.1.4 Snapshots

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_011 / URS_011 | Latest displayed trends and waveforms viewable in a separate pop-up for detailed analysis during collection. | ❌ | No detached/zoom pop-up window implemented. Current viewer is single-window. |

#### 5.1.5 Configuration

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_012 | Configuration file determining collectable trends. | ✅ | `params5.txt` (tab-separated) + `channels.trends` in `pycollect_gui_config.json`. |
| PS_COLLECT_UI_013 | Configuration file determining collectable waveforms. | ✅ | `waves5.txt` + `channels.waves` in `pycollect_gui_config.json`. |

#### 5.1.6 OffLine Mode

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_016 / URS_016 | Previously stored trends/waveforms/alarms in DRC selectable to visualize. | ❌ | No DRC playback/browser in the Qt GUI; only conversion to CSV. |
| PS_COLLECT_UI_017 / URS_017 | DRC content savable to tab-limited ASCII files. | 🟡 | `drc_2_csv.py` produces comma-separated CSV (trends + waveforms). Tab-delimited output not directly produced — add a tab-export option. |
| PS_COLLECT_UI_018 / URS_018 | Within a recorded file, select a subset of trends/waveforms for ASCII export. | ❌ | Conversion currently exports all channels; no per-channel subset selector in the export UI. |
| PS_COLLECT_UI_019 / URS_019 | Within a recorded file, select a start/end time subset for ASCII export. | ❌ | No time-range subset selector for export. |

#### 5.1.7 Labeling Requirements

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_MANUAL_001 / URS_M_001 | English electronic manual. | 🟡 | This `README.md` covers operation; no separate user manual document yet. |
| PS_COLLECT_MANUAL_002 / URS_M_002 | Manual contains intended-use statement + non-clinical warning. | ❌ | Statement currently absent from `README.md`. |

### 5.2–5.4 External / Hardware / Communication Interfaces

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_EX_INTERFACE_001 | Support DRI serial computer interface protocol. | ✅ | `pycollect.py` implements DRI framing, escape handling, checksum. |
| PS_COLLECT_EX_INTERFACE_004 | Support waveform & parameter data up to DRI_LEVEL_06. | 🟡 | Trend (DRI L01) + waveform subrecords handled; DRI level 06-specific subrecord coverage not exhaustively validated against the spec. |
| PS_COLLECT_EX_INTERFACE_003 | Output file format: tab-limited ASCII tables. | 🟡 | CSV (comma) implemented; tab-delimited variant pending. |
| PS_COLLECT_HW_INTERFACE_001 | PC with serial or USB port. | ✅ | Uses `pyserial`; works with any OS-enumerated COM port (incl. USB-serial). |
| PS_COLLECT_HW_INTERFACE_003 | Windows 10 compatibility. | ✅ | Project runs on Windows 10/11 with Python 3 + PyQt5. |
| PS_COLLECT_HW_INTERFACE_004 | Windows 11 compatibility. | ✅ | Same as above. |
| PS_COLLECT_COMM_INTERFACE_003 | Support baud rates 19200 and 115200. | ✅ | Baudrate combo in *Monitor Connection* offers both; persisted to `ui.connection.baudrate`. |
| PS_COLLECT_COMM_INTERFACE_004 | Compatibility with GEHC DRI-supporting Patient Monitors. | ✅ | Verified end-to-end against simulator; CARESCAPE COM5 path implemented. |

### Summary

| Status | Count |
|---|---|
| ✅ Implemented | 11 |
| 🟡 Partial | 6 |
| ❌ Missing | 7 |

### Top Gaps to Close Next

1. **Alarms** (PS_006 / URS_006, PS_007): add alarm subrecord parsing, storage, and display.
2. **Notes editor + persistence** (PS_009, PS_010).
3. **Offline DRC browser** (PS_016): in-GUI playback / review of stored DRC files.
4. **ASCII export refinements** (PS_017, PS_018, PS_019): tab-delimited output, channel subset, time-range subset.
5. ~~**Intended-use disclaimer** (PS_003, PS_M_002): startup banner + manual statement.~~
6. ~~**Password registration** (PS_001): authenticated unlock for ASCII conversion (legacy LabVIEW behavior).~~
7. **Snapshot pop-up window** (PS_011): detachable detailed-analysis window during live collection.
8. **Trend interval upper bound**: raise `trend_interval_spin` maximum from 120 s to 3600 s to meet PS_008.
9. **All section headers should be lockable**: currently only Monitor Connection, Session Setup, and Monitoring Control are lockable; extend to all collapsible sections.
10. **User role does not impact locking behavior yet**: the Administrator/Reviewer/Recorded role selector is present but does not enforce role-based lock policies on sections.
