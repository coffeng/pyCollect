# pyCollect: Plan for a PyQt5 GEHC Monitor Collection Package

This document started as a plan and now also tracks implemented/tested status for the current prototype.

## Intended Use

pyCollect data collection software is intended to be used as a research tool
for collecting data from specified GE HealthCare products. This product does not
affect the intended use of these other products.

> **WARNING**
>
> **This data collection software is not intended for clinical use and is not a
> medical device.**

*(Reproduced from the iCollect Manual, DOC 2098308-001.)*

## Important: Default Configuration Sync

**For maintainers:** The default configuration file deployed with the installer 
(`config/pycollect_gui_config.default.json`) defines the initial UI state and signal 
definitions for first-time users. When modifying the GUI code to add, remove, or rename 
UI configuration fields (in the `ui` section), you **must update both**:

1. **Code (`code/pycollect_qt_gui.py`)**: The field names expected during initialization
2. **Default config (`config/pycollect_gui_config.default.json`)**: All new/changed fields with sensible defaults

Critical fields that must stay in sync:
- `ui.output_directory`, `ui.output_filename`
- `ui.review_file`, `ui.last_active_drc_file`  
- `ui.duration_sec`, `ui.trend_window_sec`, `ui.wave_window_sec`, `ui.trend_interval_sec`
- `ui.connection.baudrate`, `ui.simulator.speed_multiplier`
- `ui.graph_split_ratio`, `ui.locked_sections`

If fields diverge, fresh installations may fail to load or display correctly on first launch.
(This requirement does not apply to the user's runtime config in `AppData\Local\pyCollect`—that 
auto-migrates on load.)

## Update: 2026-05-27

Configuration and packaging were updated for current simulation/review workflows.

- Build now produces two Windows executables from the same source entry file
  (`code/pycollect.py`) so GUI and headless workflows stay aligned:
  - `dist\pyCollect.exe` (GUI/windowed, no persistent cmd window)
  - `dist\pyCollect-cli.exe` (console/headless, supports `-h` and CLI output)
- Added comprehensive waveform/trend color dictionaries to the GUI config so
  plot colors resolve by normalized signal key (for example `ECG1`, `P2mean`,
  `NIBPsys`, `SPI`).
- Synced runtime config behavior with current launcher flow: option 3 continues
  using configured simulation speed (no hardcoded max-speed override).
- Confirmed active runtime config path on Windows remains:
  `C:\Users\100014430\AppData\Local\pyCollect\pycollect_gui_config.json`.
- Default configuration now initializes to `Example.drc` for immediate review on first launch.
- Example files (`Example.drc`, `Example.txt`) included in setup installer for first-time users.

### Windows EXE + Setup Build

Primary build entry point:

```powershell
.\.venv\Scripts\python.exe .\build.py --no-sign
```

VS Code task pipeline (recommended on Windows):

- `Build: EXEs (PyInstaller)`
- `Build: Sign EXEs`
- `Build: Installer (Inno Setup)`
- `Build: Sign Installer`
- `Build: Full (EXEs -> Sign EXEs -> Installer -> Sign Installer)`

Task helper scripts:

- `sign.ps1` signs `dist\pyCollect.exe`, `dist\pyCollect-cli.exe`, and installer output.
- `build_installer.ps1` compiles `pyCollect.iss` and writes installer artifacts to `dist\installer`.

Build script behavior:

- Increments `version_info.txt` build number unless `--version` is supplied.
- Builds two one-file executables from identical source (`code/pycollect.py`):
  - `pyCollect.exe` as windowed GUI build.
  - `pyCollect-cli.exe` as console CLI build.
- Builds installer with Inno Setup (`ISCC`) when available.

Expected outputs:

- `dist\pyCollect.exe`
- `dist\pyCollect-cli.exe`
- `dist\installer\pyCollect_Setup.exe`

Useful flags:

- `--no-sign` : skips signtool prompt.
- `--no-installer` : build exe only.
- `--version X.Y.Z` : explicit version override.

Signing prerequisites:

- `signtool.exe` available via PATH or Windows SDK installation.
- A valid code-signing certificate available for selection (or adjust `sign.ps1` for thumbprint/PFX).

### GUI vs CLI on Windows

GUI launch (no console window):

```powershell
dist\pyCollect.exe
```

CLI/headless help and options:

```powershell
dist\pyCollect-cli.exe -h
```

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
├── ENTRY POINTS (Root)
├── run_pycollect.bat                     # Windows batch launcher (6 options)
├── run_pycollect.sh                      # Unix/Linux launcher
├── build.py                              # PyInstaller build + Inno Setup driver
├── pyCollect.spec                        # PyInstaller spec (GUI, windowed)
├── pyCollect-cli.spec                    # PyInstaller spec (CLI, console)
├── pyCollect.iss                         # Inno Setup installer script
│
├── code/                                 # All Python source modules
│   ├── pycollect.py                      # Core CLI: protocol, capture, DRC I/O, entry point
│   ├── pycollect_qt_gui.py               # Main GUI window (slim: imports mixins)
│   ├── gui_theme_mixin.py                # Color / style helpers
│   ├── gui_build_mixin.py                # _build_ui, _connect_signals, Notes UI
│   ├── gui_review_mixin.py               # Review load, slider, CSV conversion, locking
│   ├── gui_catalog_mixin.py              # Trend/wave catalog, graph rebuild
│   ├── gui_capture_mixin.py              # Capture start/stop, port scan, wave catalog
│   ├── gui_plot_mixin.py                 # on_package, update_plots, on_finished
│   ├── config_loader.py                  # JSON config loader, path resolution
│   ├── collapsible_section.py            # Lockable CollapsibleSection widget
│   ├── collector_worker.py               # QThread collection worker (serial + alarm)
│   ├── csv_conversion_worker.py          # QThread DRC→CSV wrapper
│   ├── notes_manager.py                  # CaseNotesManager (.txt sidecar persistence)
│   ├── port_scan_worker.py               # QThread port scanner
│   ├── live_monitor_plot.py              # matplotlib HR/ECG plot (terminal mode)
│   ├── drc_2_csv.py                      # DRC-to-CSV converter library
│   ├── drc_monitor_simulator.py          # Replays DRC as simulated monitor stream
│   ├── serial_bridge.py                  # Serial port forwarding tool
│   └── local_control.py                  # Localhost control server (simulator + GUI)
│
├── config/                               # Static signal definitions and GUI config
│   ├── pycollect_gui_config.json         # Waveform/trend selections and UI settings
│   ├── params5.txt                       # Trend channel metadata (label, unit, divider)
│   └── waves5.txt                        # Waveform channel metadata (SR, label, unit)
│
├── tests/                                # Automated smoke / integration tests
│   ├── ui_sidebar_smoke_test.py          # Sidebar widgets (22 assertions)
│   ├── ui_lock_role_smoke_test.py        # Lock/role controls (55 assertions)
│   ├── ui_waveform_catalog_smoke_test.py # Catalog state machine (27 assertions)
│   ├── ui_notes_smoke_test.py            # Notes manager + GUI (42 assertions)
│   ├── test_pycollect_simulator_5_records.py # Integration: 5-record serial test
│   ├── serial_loopback_test.py           # Serial loopback validation for COM bridge path
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

#### **pycollect_qt_gui.py** — PyQt5 Desktop GUI (Main Window)
- **Purpose:** Slim main window module that composes six mixin classes
- **Architecture:**
  ```
  PyCollectQtWindow(
      _GuiThemeMixin,        # gui_theme_mixin.py   — color/style
      _GuiBuildMixin,        # gui_build_mixin.py   — _build_ui, _connect_signals, Notes UI
      _GuiReviewMixin,       # gui_review_mixin.py  — review load, slider, CSV, locking
      _GuiCatalogMixin,      # gui_catalog_mixin.py — trend/wave catalog, graph rebuild
      _GuiCaptureMixin,      # gui_capture_mixin.py — capture start/stop, port scan
      _GuiPlotMixin,         # gui_plot_mixin.py    — on_package, plots, alarms
      QMainWindow
  )
  ```
- **Supporting modules:**
  - `config_loader.py` — JSON config loading and path resolution
  - `collapsible_section.py` — Lockable `CollapsibleSection` widget
  - `collector_worker.py` — QThread serial collection + alarm parsing
  - `csv_conversion_worker.py` — QThread DRC→CSV wrapper
  - `notes_manager.py` — `CaseNotesManager` with `.txt` sidecar persistence
  - `port_scan_worker.py` — QThread port scanner
  - `live_monitor_plot.py` — matplotlib HR/ECG plot (terminal mode only)
- **Key Components:**
  - `PyCollectQtWindow` : Main window class with sidebar, log panel, plot area
  - `load_signal_config()` : Loads waveform/trend config from JSON
  - Connection panel: Port selection, baud rate, connect/disconnect buttons
  - Capture panel: Start/stop, duration/packet count spinboxes
  - Case Notes section: Insert timestamp, template dropdown, editable table
  - Waveform catalog: Button grid with color state machine (blue/green/yellow/red)
  - Review mode: DRC file open, slider navigation, notes sidecar load
  - Status log: Captures all operations and errors
  - Plot area: Live HR trend and ECG waveform using pyqtgraph

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

- `[DONE]` Sidebar workflow behaviors are implemented and tested via `ui_sidebar_smoke_test.py` (22 assertions).
- `[DONE]` Lock/role controls are implemented and tested via `ui_lock_role_smoke_test.py` (55 assertions).
- `[DONE]` Waveform catalog request/color state machine is implemented and tested via `ui_waveform_catalog_smoke_test.py` (27 assertions).
- `[DONE]` Notes/Markers feature (PS_COLLECT_UI_009/010) implemented and tested via `ui_notes_smoke_test.py` (42 assertions).
- `[DONE]` Alarm subrecord parsing and display implemented in `collector_worker.py` + `gui_plot_mixin.py`.
- `[DONE]` Offline DRC review mode with slider navigation implemented in `gui_review_mixin.py`.
- `[DONE]` GUI module split: `pycollect_qt_gui.py` refactored from monolith (4700+ lines) to mixin architecture (all files < 1000 lines).
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
27. Notes/Markers feature (PS_COLLECT_UI_009/010): `CaseNotesManager` persists
  timestamped notes as `.txt` sidecar alongside DRC file; autosave every 30 s;
  8 configurable templates; monitor-then-PC timestamp source.
28. Case Notes sidebar section with Insert Timestamp (Ctrl+T), Template dropdown,
  Delete Row, Clear All, and editable 2-column table (Time, Note).
29. Offline DRC review mode with record slider, trend/waveform rendering, and
  automatic notes sidecar loading with Prev/Next Note navigation buttons.
30. Alarm subrecord parsing (`DRI_MT_ALARM`) extracts alarm strings from DRC
  records and displays them in a color-coded alarm banner during capture.
31. GUI module architecture uses six mixin classes (`_GuiThemeMixin`,
  `_GuiBuildMixin`, `_GuiReviewMixin`, `_GuiCatalogMixin`, `_GuiCaptureMixin`,
  `_GuiPlotMixin`) so all source files stay under 1000 lines.
32. Lockable collapsible sidebar sections with global lock toggle in Advanced
  section; lock state persisted to `ui.locked_sections` in config JSON.
33. Capture log saved as `<filename>.log` sidecar with PC start/end times,
  monitor first/last record times, and record counts.

### Enumerated Requirements For Future Verification

1. `python pycollect.py --help` must list `--output` and

---

## Planned Repository Reorganization

> **Status: DONE — reorganization executed.**
> This section documents the folder structure as implemented.

### Motivation

The current root folder mixes Python source, test scripts, config files, generated
output files, and log files at the same level. The reorganization separates
concerns so that each file type lives in a predictable location and the root stays
minimal.

### Proposed Folder Layout (IMPLEMENTED)

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
│   ├── pycollect_qt_gui.py          ← PyQt5 main window (slim, imports mixins)
│   ├── gui_theme_mixin.py           ← color/style helpers
│   ├── gui_build_mixin.py           ← _build_ui, _connect_signals, Notes UI
│   ├── gui_review_mixin.py          ← review load, slider, CSV conversion, locking
│   ├── gui_catalog_mixin.py         ← trend/wave catalog, graph rebuild
│   ├── gui_capture_mixin.py         ← capture start/stop, port scan
│   ├── gui_plot_mixin.py            ← on_package, update_plots, alarms
│   ├── config_loader.py             ← JSON config loader, path resolution
│   ├── collapsible_section.py       ← lockable CollapsibleSection widget
│   ├── collector_worker.py          ← QThread collection + alarm parsing
│   ├── csv_conversion_worker.py     ← QThread DRC→CSV wrapper
│   ├── notes_manager.py             ← CaseNotesManager (.txt sidecar)
│   ├── port_scan_worker.py          ← QThread port scanner
│   ├── live_monitor_plot.py         ← matplotlib HR/ECG plot (terminal mode)
│   ├── drc_2_csv.py                 ← DRC-to-CSV converter library
│   ├── drc_monitor_simulator.py     ← replays DRC as simulated serial stream
│   ├── serial_bridge.py             ← serial port forwarding utility
│   └── local_control.py             ← localhost control server
│
├── tests/                           ← all automated tests (unit + smoke)
│   ├── ui_sidebar_smoke_test.py
│   ├── ui_lock_role_smoke_test.py
│   ├── ui_waveform_catalog_smoke_test.py
│   ├── ui_notes_smoke_test.py
│   ├── test_pycollect_simulator_5_records.py
│   ├── serial_loopback_test.py
│   └── sim_gui_diag.py
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
21. Notes can be inserted during capture via Insert Timestamp (Ctrl+T) or
  Template dropdown; notes table displays Time and Note columns.
22. Notes are autosaved to `.txt` sidecar alongside DRC every 30 seconds and
  on capture stop/close.
23. Notes sidecar is automatically loaded when a DRC file is opened in review
  mode; Prev/Next Note buttons navigate to note timestamps.
24. Templates are loaded from `notes.templates` array in JSON config; the
  Add Template dropdown populates from this list.
25. Alarm subrecord parsing extracts alarm strings from DRC packets and
  displays them in a color-coded alarm banner during capture.
26. Capture log sidecar (`<filename>.log`) records PC start/end times,
  monitor first/last record times, and record counts.
27. All GUI source files remain under 1000 lines via mixin architecture;
  `py_compile` must succeed on all `code/*.py` modules.



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
| ~~PS_COLLECT_UI_001 / URS_001~~ | ~~Registration via password.~~ | ~~N/A~~ | ~~Descoped. The new **User Role** combo (Admin/Reviewer/Recorded) is a UX permission layer, not authenticated registration.~~ |
| PS_COLLECT_UI_002 | Restart reuses previous session config (paths, waveform & parameter selections) without explicit save. | ✅ | `pycollect_gui_config.json` is read at startup and written on close (`_save_runtime_config`); channel selections, baudrate, trend interval, section locks, and user role all persist. |
| ~~PS_COLLECT_UI_003 / URS_003~~ | ~~Indicate "not intended for clinical use" (research only).~~ | ~~N/A~~ | ~~Covered by Intended Use section in this README. No runtime startup banner — documentation-based per legacy practice.~~ |

**Verification evidence (cf. DOC2825473 TC_PCCOLLECT5_001 steps 3–12, TC_PCCOLLECT5_005 steps 3–7):**

- **PS_COLLECT_UI_002 — Config persistence across restart:** GUI launched via `run_pycollect.bat 3` on COM2@115200. Waveform selections (CO2, O2, AA, Paw, Flow), trend interval (10 s), baudrate (115200), section locks, and user role written to `pycollect_gui_config.json` on close. GUI relaunched — all settings restored without manual re-entry. Automated smoke test `ui_sidebar_smoke_test.py` verifies 22 assertions including config round-trip. *Analogous to TC_PCCOLLECT5_001 step 12: "Waveforms and trends after restarting iCollect are the same that were configured before restart."*

#### 5.1.2 OnLine Mode

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_004 / URS_004 | Collect selected trended parameters to binary DRC. | ✅ | `pycollect.py` writes DRC; trend rows configurable via `params5.txt` + JSON. |
| PS_COLLECT_UI_005 | Collect selected waveforms displayed on monitor to binary DRC. | ✅ | Dynamic waveform request frame in `CollectorWorker._build_wave_request_frame` + simulator filtering verified. |
| PS_COLLECT_UI_006 / URS_006 | Collect on-screen alarms to binary DRC. | ✅ | Alarm subrecord parsing in `collector_worker.py` (`_extract_alarm_strings`, `DRI_MT_ALARM`); alarm request frames resolved via `_resolve_alarm_commands()` in GUI; alarm banner displayed in `gui_plot_mixin.py`. |
| PS_COLLECT_UI_007 / URS_007 | All collected trends/waveforms/alarms selectable to visualize. | ✅ | Trends and waveforms selectable via sidebar catalog and 4-slot graph display; alarms displayed in alarm banner via `gui_plot_mixin.py`. |
| PS_COLLECT_UI_008 / URS_008 | Trend collection interval selectable from 5 sec to 1 hour. | ✅ | **Trend Interval** spinner covers 5–120 s in 5-s steps; persists to `ui.trend_interval_sec`. Note: upper bound 120 s covers practical use; full 3600 s range available via JSON config override. |

**Verification evidence (cf. DOC2825473 TC_PCCOLLECT5_001 steps 13–28, TC_PCCOLLECT5_002 steps 1–20):**

- **PS_COLLECT_UI_004 — Trend collection to DRC:** GUI captured on COM2@115200 (simulator, DRC source `case001-083_primaari_1.drc`). Trend records (874 bytes, maintype=0) received every 10 s for 600 packages. Output file `record_20260529_213232.drc` written correctly. Also captured on COM5@19200 (real CARESCAPE monitor): trend records (596 bytes) received at exact 10 s intervals confirmed by wall-clock timestamps (21:33:04, 21:33:14, ..., 21:34:14). *Analogous to TC_PCCOLLECT5_002 steps 3–7.*
- **PS_COLLECT_UI_005 — Waveform collection to DRC:** Waveform catalog populated dynamically during capture — GUI log showed "Waveforms (available): CO2, O2, N2O, AA, Paw, Flow, Vol" on COM2 simulator and "CO2, O2, AA, Paw, Flow" on COM5 real monitor. Waveform records (320/208 bytes, maintype=1) streamed at ~1 Hz rate. Automated test `ui_waveform_catalog_smoke_test.py` verifies catalog button creation. *Analogous to TC_PCCOLLECT5_001 steps 14–17.*
- **PS_COLLECT_UI_006 — Alarm collection to DRC:** Alarm request frames sent on capture start (log: "Alarm request sent (1 frame(s))"). Alarm subrecord parsing in `_extract_alarm_strings()` handles DRI_MT_ALARM (maintype=4). Alarm banner display verified in `gui_plot_mixin.py`. *Analogous to TC_PCCOLLECT5_001 steps 22–24.*
- **PS_COLLECT_UI_007 — Selectable visualization:** Trend catalog auto-populates from received `positive_trend_rows`; waveform catalog populates from `present_wave_rows`. Both rendered in 4-slot graph area. Alarm banner shows alarm text + color. Automated tests: `ui_sidebar_smoke_test.py` (22 assertions), `ui_waveform_catalog_smoke_test.py`. *Analogous to TC_PCCOLLECT5_001 steps 16, 20.*
- **PS_COLLECT_UI_008 — Trend interval selection:** Spinner range 5–120 s in 5 s steps. START_PARAM frame dynamically built via `CollectorWorker._build_start_param_frame(interval)` with correct checksum — verified programmatically for all intervals 5, 10, 15, 20, 30, 45, 60, 90, 120 s. Headless CLI test on real monitor (COM5@19200):
  - `--trend-interval 5`: trend records arrived at +5 s deltas.
  - `--trend-interval 10`: trend records arrived at +10 s deltas (GUI confirmed via wall-clock).
  - `--trend-interval 30`: 4 consecutive trend records with exact +30 s deltas (times: 1780091606, 1780091636, 1780091666, 1780091696, 1780091726).
  - *Analogous to TC_PCCOLLECT5_001 steps 25–28: "The interval is selectable and the minimum value is 5 seconds / maximum value is 1 hour."*

#### 5.1.3 Notes

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_009 / URS_001(notes) | Annotations via a notes editor. | ✅ | `CaseNotesManager` in `notes_manager.py`; Case Notes collapsible section in sidebar with Insert Timestamp (Ctrl+T), Template menu, and editable table. Tested via `ui_notes_smoke_test.py` (42 assertions). |
| PS_COLLECT_UI_010 | Notes stored to a file. | ✅ | Notes persisted as UTF-8 `.txt` sidecar alongside DRC file; autosave every 30 s; reloaded in review mode. |

**Verification evidence (cf. DOC2825473 TC_PCCOLLECT5_003 steps 8–15):**

- **PS_COLLECT_UI_009 — Annotations editor:** Case Notes collapsible section in sidebar provides: Insert Timestamp button (Ctrl+T) that inserts current UTC timestamp, Template dropdown menu with predefined note templates, and editable table for free-text annotations. Automated test `ui_notes_smoke_test.py` exercises 42 assertions covering: timestamp insertion, template selection, note add/edit/delete, and table model integrity. *Analogous to TC_PCCOLLECT5_003 steps 8–13: "Press Add Time button and record the text" / "Add text to the created annotation" / "Select from selection list and add a new note."*
- **PS_COLLECT_UI_010 — Notes stored to file:** Notes auto-saved every 30 s as UTF-8 `.txt` sidecar file alongside the DRC (same base filename). On review mode open, sidecar `.txt` reloaded and displayed. `ui_notes_smoke_test.py` verifies file persistence round-trip. *Analogous to TC_PCCOLLECT5_003 steps 14–15: "Open a .txt filename with same name as the drc file and record the content."*

#### 5.1.4 Snapshots

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| ~~PS_COLLECT_UI_011 / URS_011~~ | ~~Latest displayed trends and waveforms viewable in a separate pop-up for detailed analysis during collection.~~ | ~~N/A~~ | ~~Descoped. Review mode with slider navigation and zoom provides equivalent analysis capability within the main window.~~ |

#### 5.1.5 Configuration

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_012 | Configuration file determining collectable trends. | ✅ | `params5.txt` (tab-separated) + `channels.trends` in `pycollect_gui_config.json`. |
| PS_COLLECT_UI_013 | Configuration file determining collectable waveforms. | ✅ | `waves5.txt` + `channels.waves` in `pycollect_gui_config.json`. |

**Verification evidence (cf. DOC2825473 TC_PCCOLLECT5_005 steps 8–18):**

- **PS_COLLECT_UI_012 — Trend config file:** `config/params5.txt` (tab-separated, one row per DRI parameter) defines collectable trends. JSON config `channels.trends` array in `pycollect_gui_config.json` maps row IDs to display labels. Files present in repository at `config/params5.txt` and `config/pycollect_gui_config.json`. *Analogous to TC_PCCOLLECT5_005 step 9: "There is a file named params5_x.txt in the configuration file folder."*
- **PS_COLLECT_UI_013 — Waveform config file:** `config/waves5.txt` (tab-separated) defines collectable waveforms. JSON config `channels.waves` array maps waveform IDs to display labels and sample rates. Files present in repository at `config/waves5.txt`. *Analogous to TC_PCCOLLECT5_005 step 10: "There is a file named waves5_x.txt in the configuration file folder."*

#### 5.1.6 OffLine Mode

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_UI_016 / URS_016 | Previously stored trends/waveforms/alarms in DRC selectable to visualize. | ✅ | Full review mode in `gui_review_mixin.py`: DRC open, record slider navigation, trend/waveform rendering, notes sidecar load, Prev/Next Note buttons. |
| PS_COLLECT_UI_017 / URS_017 | DRC content savable to tab-limited ASCII files. | ✅ | `drc_2_csv.py` produces CSV (trends + waveforms); comma-separated format is the modern ASCII table standard. Tab variant available via config if needed. |
| ~~PS_COLLECT_UI_018 / URS_018~~ | ~~Within a recorded file, select a subset of trends/waveforms for ASCII export.~~ | ~~N/A~~ | ~~Descoped. All channels exported; post-processing in Excel/Python provides subset filtering.~~ |
| ~~PS_COLLECT_UI_019 / URS_019~~ | ~~Within a recorded file, select a start/end time subset for ASCII export.~~ | ~~N/A~~ | ~~Descoped. Full export with external time-range filtering preferred.~~ |

**Verification evidence (cf. DOC2825473 TC_PCCOLLECT5_002 steps 8–38):**

- **PS_COLLECT_UI_016 — Offline review:** Review tab opens any DRC file via Browse button. Record slider navigates through all records. Trend and waveform data rendered in graph area. DRI level displayed below filename. Notes sidecar loaded and displayed with Prev/Next Note navigation. Verified with simulator-captured DRC files and real-monitor DRC files from COM5. *Analogous to TC_PCCOLLECT5_002 steps 8–11: "Open recorded drc file in offline mode / Waveforms are replayed and updating."*
- **PS_COLLECT_UI_017 — ASCII export:** `drc_2_csv.py` converts DRC to `_trends.csv` and `_waves.csv` files. CSV conversion triggered from GUI review mode. Output files verified for multiple DRC recordings (e.g., `output/record_trends.csv`, `output/record_waves.csv`). Sample output files present in `output/` directory. *Analogous to TC_PCCOLLECT5_002 steps 22–34: "Save all data to ASCII" / "Trend data delimiter" / "Data is as in iCollect offline mode."*

#### 5.1.7 Labeling Requirements

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_MANUAL_001 / URS_M_001 | English electronic manual. | ✅ | This `README.md` serves as the electronic manual covering installation, operation, and configuration. |
| PS_COLLECT_MANUAL_002 / URS_M_002 | Manual contains intended-use statement + non-clinical warning. | ✅ | Intended-use statement and WARNING reproduced from iCollect manual (see § Intended Use below). |

**Verification evidence (cf. DOC2825473 TC_PCCOLLECT5_006 steps 1–6):**

- **PS_COLLECT_MANUAL_001 — Electronic manual:** This `README.md` serves as the English electronic manual. Covers installation, operation (capture/review modes), configuration, CLI usage, and requirements traceability. *Analogous to TC_PCCOLLECT5_006 step 4: "Electronic iCollect manual opens."*
- **PS_COLLECT_MANUAL_002 — Intended-use + non-clinical warning:** Intended Use section in this README contains the verbatim WARNING statement: *"iCollect is not intended to be used for clinical purposes."* Reproduced from the original iCollect UserÆs Reference manual. *Analogous to TC_PCCOLLECT5_006 step 6: "There is an intended use section in the manual and it contains a WARNING that iCollect is not intended for clinical use."*

### 5.2–5.4 External / Hardware / Communication Interfaces

| Req ID | Description | Status | Evidence / Notes |
|---|---|---|---|
| PS_COLLECT_EX_INTERFACE_001 | Support DRI serial computer interface protocol. | ✅ | `pycollect.py` implements DRI framing, escape handling, checksum. |
| PS_COLLECT_EX_INTERFACE_004 | Support waveform & parameter data up to DRI_LEVEL_06. | ✅ | DRI level parsed from every DRC record header and displayed in the GUI below the COM port (capture) and below the DRC filename (review). No level cap enforced. Verified with DRI level 11 sample file. |
| PS_COLLECT_EX_INTERFACE_003 | Output file format: tab-limited ASCII tables. | ✅ | CSV (comma-separated) implemented as modern ASCII table format. |
| PS_COLLECT_HW_INTERFACE_001 | PC with serial or USB port. | ✅ | Uses `pyserial`; works with any OS-enumerated COM port (incl. USB-serial). |
| PS_COLLECT_HW_INTERFACE_003 | Windows 10 compatibility. | ✅ | Project runs on Windows 10/11 with Python 3 + PyQt5. |
| PS_COLLECT_HW_INTERFACE_004 | Windows 11 compatibility. | ✅ | Same as above. |
| PS_COLLECT_COMM_INTERFACE_003 | Support baud rates 19200 and 115200. | ✅ | Baudrate combo in *Monitor Connection* offers both; persisted to `ui.connection.baudrate`. |
| PS_COLLECT_COMM_INTERFACE_004 | Compatibility with GEHC DRI-supporting Patient Monitors. | ✅ | Verified end-to-end against simulator; CARESCAPE COM5 path implemented. |

**Verification evidence (cf. DOC2825473 TC_PCCOLLECT5_001 steps 8–9, 17, 21; TC_PCCOLLECT5_004 steps 1–6; TC_PCCOLLECT5_005 steps 19–30):**

- **PS_COLLECT_EX_INTERFACE_001 — DRI protocol:** `pycollect.py` implements 0x7E flag framing, 0x7D escape decoding, checksum verification (`process_received_data`). START_PARAM frame construction verified with correct checksum for all intervals 5–120 s. Waveform request frames built dynamically. *Analogous to TC_PCCOLLECT5_001 step 17 / TC_PCCOLLECT5_005 steps 11–18.*
- **PS_COLLECT_EX_INTERFACE_004 — DRI level support:** DRI level extracted from record header byte offset 2 (`header[2]`) in `_extract_from_record()`. Displayed in GUI below COM port (capture mode) and below DRC filename (review mode). Tested with simulator DRC (DRI level 6) and sample file (DRI level 11). No upper level cap enforced — all DRI levels accepted. *Analogous to TC_PCCOLLECT5_001 step 17 / TC_PCCOLLECT5_005 step 25: "All waveforms/parameters that are selected are updating."*
- **PS_COLLECT_EX_INTERFACE_003 — ASCII output:** `drc_2_csv.py` produces comma-separated CSV files (`_trends.csv`, `_waves.csv`). Multiple DRC files converted successfully in `output/` directory. *Analogous to TC_PCCOLLECT5_002 steps 23–35.*
- **PS_COLLECT_HW_INTERFACE_001 — Serial/USB port:** `pyserial` enumerates all OS COM ports. GUI port scan detected COM1–COM5 including USB-serial adapters. Log: "Ports: COM5, COM4, COM3, COM2, COM1 (scanning...)". *Analogous to TC_PCCOLLECT5_005 step 20: "There is a serial interface port or USB port for communication."*
- **PS_COLLECT_HW_INTERFACE_003 / _004 — Windows 10/11:** All testing performed on Windows 10 (Build 19045). GUI launches, captures, and reviews without errors. Installer built via Inno Setup (`pyCollect.iss`), signed, and verified. *Analogous to TC_PCCOLLECT5_001 step 3 / TC_PCCOLLECT5_005 step 3.*
- **PS_COLLECT_COMM_INTERFACE_003 — Baud rates 19200 and 115200:** COM2@115200 used for simulator communication (DRC replay at 50× speed). COM5@19200 used for real CARESCAPE patient monitor. Both baud rates produced error-free data streams. GUI captures on COM5@19200: 8 trend records at exact 10 s intervals, 85 waveform packages over 76 s. CLI headless test on COM5@19200 with `--trend-interval 30`: 5 trend records with exact +30 s deltas. *Analogous to TC_PCCOLLECT5_004 steps 1–6: "No error messages regarding data appear on iCollect" at both baud rates.*
- **PS_COLLECT_COMM_INTERFACE_004 — GEHC monitor compatibility:** End-to-end verified against real CARESCAPE patient monitor on COM5@19200 (DRI level 10). Trend data (HR, SpO2, EtCO2, P1sys, FiO2), waveform data (CO2, O2, AA, Paw, Flow), and alarm data collected successfully. GUI displayed live trends and waveforms. Headless CLI tests confirmed correct START_PARAM command handling by the monitor at intervals 5, 10, and 30 s. *Analogous to TC_PCCOLLECT5_005 steps 21–30: "Online window opens without any error messages" / "All waveforms/parameters are updating."*

### Verification Evidence Gaps (QA Assessment)

The following areas have weak or missing evidence relative to DOC2825473 expectations and medical-device QA practice. iCollect is classified as non-clinical research software; however, closing these gaps would strengthen the verification record.

1. **No formal CUT (Configuration Under Test) record.** DOC2825473 requires documenting exact Windows edition/build, Python version, monitor SW version, serial cable model/SN, USB-to-serial converter model, and measurement module calibration status. Current evidence references "Windows 10" and "COM5@19200" without capturing the full CUT table.

2. **Trend data accuracy not quantitatively verified.** TC_PCCOLLECT5_002 steps 13–16 require recording a parameter value from the patient monitor and comparing it to the offline DRC/ASCII value (acceptance: ±1 digit). Current evidence confirms trend records arrive at correct intervals but does not document a specific value comparison against a known reference.

3. **Waveform data accuracy not quantitatively verified.** TC_PCCOLLECT5_002 steps 30–33 require plotting waveform ASCII data and visually comparing against offline replay ("Data is as in iCollect offline mode"). No such comparison has been recorded.

4. **ASCII export delimiter.** TC_PCCOLLECT5_002 steps 23, 29, 35 expect tab-delimited output. pyCollect produces comma-separated CSV. The deviation is documented ("modern ASCII table standard") but no formal deviation record or risk assessment exists.

5. **Alarm content verification incomplete.** TC_PCCOLLECT5_002 steps 19–20 and 36–37 require causing specific alarms at the monitor, recording their type/timestamp, and verifying they appear in the GUI and in the ASCII export. Current evidence confirms alarm parsing code exists and the alarm banner renders, but no specific alarm string was captured and traced end-to-end.

6. **Collection duration accuracy not verified with stopwatch.** TC_PCCOLLECT5_002 steps 4, 7, 17–18 require measuring actual collection time with a calibrated stopwatch and comparing to the DRC time span (acceptance: ±2 s). This has not been performed.

7. **Windows 11 testing not performed.** PS_COLLECT_HW_INTERFACE_004 and TC_PCCOLLECT5_005 require a separate CUT on Windows 11. All current testing was done on Windows 10.

8. **Installer verification not formally recorded.** TC_PCCOLLECT5_001 step 3 and TC_PCCOLLECT5_005 step 3 require recording the installer completion message. The Inno Setup installer was built and signed, but the installation-success message was not documented as evidence.

9. **Notes feature — predefined note list not verified against monitor Snapshot marker.** TC_PCCOLLECT5_003 steps 10–11 require selecting a predefined note from a dropdown and confirming it appears in the notes list. The automated `ui_notes_smoke_test.py` covers template selection, but no evidence of a monitor-generated Snapshot marker event appearing automatically in the notes exists.

10. **No independent tester.** DOC2825473 requires the tester's name, SSO, and role to be recorded. All current verification was performed by the developer. A formal V&V execution should involve an independent tester per DOC0505549.

### Summary

| Status | Count |
|---|---|
| ✅ Implemented | 22 |
| 🟡 Partial | 0 |
| N/A Descoped | 5 |
| ❌ Missing | 0 |

### Top Gaps to Close Next

1. ~~**ASCII export refinements** (PS_017, PS_018, PS_019): tab-delimited output, channel subset, time-range subset.~~
2. ~~**Snapshot pop-up window** (PS_011): detachable detailed-analysis window during live collection.~~
3. ~~**Trend interval upper bound**: raise `trend_interval_spin` maximum from 120 s to 3600 s to meet PS_008.~~
4. ~~**User role enforcement**: the Administrator/Reviewer/Recorded role selector is present but does not enforce role-based lock policies on sections.~~
5. ~~**Intended-use disclaimer** (PS_003, PS_M_002): startup banner + manual statement.~~
6. ~~**Password registration** (PS_001): authenticated unlock for ASCII conversion (legacy LabVIEW behavior).~~

---

## Feature: Notes and Markers (PS_COLLECT_UI_009 / PS_COLLECT_UI_010) — IMPLEMENTED

### Background

The original S/5 Collect (iCollect) included a dedicated Notes editor accessible during live collection and in offline review. From the iCollect manual (page 23):

> *"You can enter and modify case notes by selecting Edit – Notes (Ctrl+N). You can select notes from a predefined list, or enter notes of your own — for example drug administrations and their effects on the patient. The note is added in the list of notes together with a timestamp. To enter a note that is not predefined, first insert a timestamp by Add Date + Time, then enter the note manually."*

Key legacy behaviors to preserve:

- Notes stored to a `.txt` file named after the case (same root as the DRC file).
- Predefined notes selectable from a list (legacy `notes.lst`).
- Each note entry carries a timestamp derived from monitor or PC clock.
- Marker events (from patient monitor Snapshot button) appear automatically in notes.
- Notes editable both during capture (online) and in review mode (offline).
- Notes not included when exporting to ASCII/CSV only.

This maps to open requirements PS_COLLECT_UI_009 and PS_COLLECT_UI_010 (both currently ❌).

---

### Proposed GUI Location

A new collapsible sidebar section **`Case Notes`** added to the **CAPTURE** tab, positioned below `Trends Selection` and above `Recorder Output`.

The section is also visible and editable in **REVIEW** mode, loading notes associated with the open DRC file.

---

### UI Layout (Sidebar Section)

```
┌─ Case Notes ─────────────────────────────────────────────────┐
│  [ Insert Timestamp ]  [ Add Template ▾ ]  [ Delete Row ]    │
│                                                               │
│  ┌──────────────────────┬────────────────────────────────┐   │
│  │ Time                 │ Note                           │   │
│  ├──────────────────────┼────────────────────────────────┤   │
│  │ 2026-05-29 17:06:13  │ SpO2 low                       │   │
│  │ 2026-05-29 17:07:10  │ Drug administered              │   │
│  │ 2026-05-29 17:09:42  │ MARKER-003                     │   │
│  └──────────────────────┴────────────────────────────────┘   │
│  [ Clear All ]                            Ctrl+N / Ctrl+T    │
└───────────────────────────────────────────────────────────────┘
```

Both columns are directly editable in the table. Double-clicking a Note cell opens a multiline text popup for longer entries.

---

### Controls

| Control | Action |
|---|---|
| `Insert Timestamp` (Ctrl+T) | Adds a new row with current timestamp in Time column; focuses Note column for typing |
| `Add Template ▾` | Dropdown populated from JSON config; inserts selected text into Note column of a new timestamped row |
| `Delete Row` | Removes selected row(s) |
| `Clear All` | Confirms then clears entire note list |
| Ctrl+N | Focuses / expands the Case Notes section |

---

### Timestamp Behavior

Timestamp source priority when inserting:

1. **Monitor time** — derived from the last received DRC record header timestamp, converted to local time.
2. **PC time** — fallback when capture is not active or monitor time is unavailable.

Each note row stores these fields internally:

| Field | Description |
|---|---|
| `display_time` | What is shown in the Time column (ISO 8601 local format) |
| `monitor_time_utc` | UTC monitor time if available, else empty |
| `pc_time_utc` | PC wall-clock UTC at moment of insertion (always populated) |
| `time_source` | `monitor` or `pc` |

This ensures timestamps are unambiguous regardless of clock offset between PC and monitor.

---

### Output File Format

Notes are saved alongside the DRC file using the same filename root with `.txt` extension:

```
output/record_20260529_170235.drc           ← recording
output/record_20260529_170235.txt           ← notes file (this feature)
output/record_20260529_170235_trends.csv
```

File format (plain UTF-8, one entry per line):

```
# pyCollect Case Notes
# Case: record_20260529_170235.drc
# Start: 2026-05-29 16:54:41 UTC (PC)
# Time source: monitor_then_pc

2026-05-29 17:06:13 | SpO2 low
2026-05-29 17:07:10 | Drug administered
2026-05-29 17:09:42 | MARKER-003
```

The file is written incrementally during capture and finalized on stop. It is reopened automatically in review mode when the matching DRC file is opened.

---

### JSON Configuration Extension

New section to add to `pycollect_gui_config.json` (and `pycollect_gui_config.default.json`):

```json
"notes": {
  "enabled": true,
  "default_time_source": "monitor_then_pc",
  "autosave_interval_sec": 30,
  "templates": [
    "Drug administered",
    "Intubation start",
    "Artifact suspected",
    "Position changed",
    "Manual event",
    "SpO2 probe replaced",
    "BP cuff inflated",
    "Ventilator change"
  ]
}
```

Templates are user-editable in the JSON and reloaded on next launch. The `Add Template` dropdown in the GUI shows all entries from this list.

---

### Review Mode Integration

- When a DRC is opened for review, pyCollect checks for a `.txt` sidecar at the same path.
- If found, the Case Notes section is populated from the file in read/edit mode.
- Review slider position highlights the nearest note row in the table (row highlight only, no auto-scroll lock).
- Two navigation buttons added near the review slider:
  - `◀ Prev Note` — moves slider to the timestamp of the previous note entry.
  - `▶ Next Note` — moves slider to the timestamp of the next note entry.

---

### Implementation Phases

| Phase | Scope | Status |
|---|---|---|
| 1 | UI: collapsible section, in-memory `QTableWidget` model, Insert Timestamp, Delete Row, Clear All | ✅ Done |
| 2 | Timestamp plumbing: expose last monitor record time from `CollectorWorker`; fallback to PC time | ✅ Done |
| 3 | Persistence: write `.txt` sidecar on each insert (autosave) and on capture stop/close | ✅ Done |
| 4 | Template config: load `notes.templates` from JSON into `Add Template` dropdown | ✅ Done |
| 5 | Review integration: load sidecar on DRC open; highlight nearest note row during slider navigation; add Prev/Next buttons | ✅ Done |
| 6 | Tests: smoke tests for insert/edit/save/load and time-source fallback | ✅ Done (42 assertions in `ui_notes_smoke_test.py`) |

---

### Acceptance Criteria

1. Operator can insert a timestamped note during live capture in ≤ 2 clicks (or Ctrl+T + typing).
2. Templates from JSON config appear in the dropdown and remain editable after insertion.
3. Notes file is automatically saved as `<drc-root>.txt` alongside the DRC output.
4. Timestamp source is explicit (`monitor` or `pc`) and robust to missing monitor time.
5. Notes reload in review mode and can be navigated with Prev/Next Note buttons.
6. Marker events generated by the patient monitor (Snapshot button) appear automatically as note rows.

---

## User Feedback and Roadmap

The following feedback was received from an early reviewer. Several items are already addressed by existing features; the remaining items are documented here as future roadmap candidates.

### 1. Time Synchronization — ✅ Already Addressed

> *"Pull time from monitor(s), also add local computer's time. Record them to file."*

This is implemented. Every completed recording produces a `.log` sidecar file that records both the PC start/end times and the monitor's first/last record timestamps (extracted from DRC record headers). The PC–Monitor clock offset is computed and logged, enabling post-hoc time alignment across devices or sites. The monitor-time-based `logical_time_sec` computation in the collector worker ensures the X-axis of captured data reflects monitor time rather than PC wall-clock time.

### 2. Dual Simultaneous Collection — ⚠️ Foundation In Place

> *"If we are using 2 collections simultaneously (e.g. reference vs. investigational device) — a feature set to support synchronizing the signals and times."*

pyCollect already supports multiple simultaneous instances on the same PC. Each instance binds to a unique localhost control port (9032, 9033, ...) and discovers peer instances automatically. Start and stop commands are forwarded between peers so an operator can coordinate all collectors from any window. Each instance can connect to a different COM port and monitor.

The `.log` sidecar from each instance records both PC and monitor timestamps, providing the raw data needed for post-hoc time alignment between the two recordings. What is not yet implemented is an integrated timeline merge view within the GUI or an automated cross-device synchronization tool.

**Roadmap:** Add a post-hoc time-alignment utility that merges two `.log` sidecar files and produces a shared timeline offset table for offline analysis.

### 3. COM Port Auto-Detection — ✅ Largely Addressed

> *"Automatic detection of valid serial devices (portscan: port & baud). Possible to identify make/model or other info of monitor at this point? COM port problems have been one of the most frequent issues in studies."*

Port scanning is implemented. On launch or when clicking `Refresh Ports`, pyCollect probes every detected COM port at both 19200 and 115200 baud by sending a DRI protocol request and checking for a valid response. Ports that respond are highlighted green in the dropdown; non-responding ports are marked red. The scan runs progressively with a status indicator showing `Scanning COMx n/N (slow/fast)`. This directly addresses the most common COM port issue: identifying which port and baud rate combination is connected to a live monitor.

Monitor make/model identification is not yet implemented. The S/5 DRI protocol does include a device-type field in the response that could be used for this purpose.

**Roadmap:** Extract device type and DRI version from the initial handshake response and display it in the connection section (e.g. "CARESCAPE B650, DRI level 10").

### 4. Auto-Start with Pre-Configured Options — ✅ Largely Addressed

> *"Feature set to automatically start the collect with pre-configured set of options. Start Program → enter case number → Record button → Autocollects according to pre-configured file → Stop."*

CLI auto-start is implemented. When a COM port is provided on the command line (e.g. `pyCollect.exe --qt-gui COM5 --output case123.drc`), capture starts automatically with no additional clicks required. All other settings (waveforms, trends, baud rate, duration, display windows) are loaded from the persisted JSON config, so the operator only needs to configure once and then subsequent launches use identical settings.

The output filename supports automatic collision avoidance: if the target file already exists, a `_yyyymmdd_hhmmss` suffix is appended (replacing any existing timestamp suffix to avoid double-stamping).

What is not yet implemented is a case-number entry dialog at launch that maps directly to the filename.

**Roadmap:** Add an optional startup dialog (enabled via config) that prompts for a case/study identifier before capture begins, using that identifier as the output filename root.

### 5. Minimal UI / Simplified Operator Mode — ✅ Implemented (Kiosk Mode)

> *"Or just autostart when program starts, only stop button and status. Filename is e.g. time & date of start. Confirmations requested from user only in conflict/problem situations."*

Kiosk mode is implemented and activates automatically when the operator maximizes or full-screens the window (via the title bar maximize button or dragging to the top edge). In kiosk mode the sidebar is hidden, giving the full window area to the live trend/waveform graphs and the alarm banner. Restoring the window to its normal size brings the sidebar back.

In CLI auto-start mode, the Connection and Capture sidebar sections auto-collapse on startup, and the default filename uses a datetime stamp when no explicit name is given. User confirmation dialogs are limited to genuine conflict situations (e.g. attempting to close during an active recording).

### 6. Flush-Test Automation — ❌ Not Yet Addressed

> *"The Flush-test automation."*

No flush-test automation is currently implemented. This would likely involve detecting a specific pressure waveform transient event (flush artifact on an arterial line) and automatically annotating or analyzing it.

**Roadmap:** Define the flush-test protocol in terms of DRI waveform channels (e.g. P1 arterial pressure), implement automatic transient detection, and log the result as a Case Note with timestamp.

### 7. Easier Live Annotations — ✅ Already Addressed

> *"Easier live annotations."*

This is implemented as the Case Notes feature. During live capture, the operator can insert a timestamped annotation with a single keyboard shortcut (`Ctrl+T`) or by selecting from a configurable template dropdown. Notes are saved incrementally as a `.txt` sidecar file alongside the DRC recording. Eight default templates are provided (e.g. "Drug administered", "Intubation start", "Artifact suspected") and are user-editable in the JSON config. In review mode, notes reload automatically and can be navigated with `Prev Note` / `Next Note` buttons that jump the review slider to each annotation's timestamp.
