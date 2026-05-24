# pyCollect: Plan for a PyQt5 GEHC Monitor Collection Package

This document is a plan only. It does not implement code.

## Goal

Create a Python package and desktop application that:

1. Reads GEHC patient monitor data from serial port.
2. Stores captured data as DRC files.
3. Converts DRC to CSV (and supports CSV-to-DRC where needed).
4. Provides a PyQt5 UI with workflow quality similar to PCS Annotation Tool (clear panels, guided workflow, persistent state, robust validation).
5. Replaces the old LabVIEW iCollect workflow with a maintainable Python/PyQt5 equivalent.

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

## Target Scope (What This Project Should Deliver)

1. Python package for serial capture and DRC handling.
2. PyQt5 desktop UI for capture, monitoring, and conversion tasks.
3. CLI entry points for headless operation and automation.
4. Logging, error handling, and reproducible outputs.
5. Basic test suite for packet processing and conversion correctness.

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

Acceptance criteria:
- Installable package with executable app entry point.
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

1. Legacy Python scripts are copied and documented in this repository.
2. PyQt5 app performs connect -> capture -> save DRC -> convert to CSV.
3. Core parsing and conversion paths have automated tests.
4. Operator can resume prior session settings safely.
5. Documentation describes migration from old LabVIEW workflow to Python.

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

Example command:

```bash
python drc_monitor_simulator.py --drc "C:\Users\100014430\Documents\GitLab\algorithms-tools\iCollect\Example.drc" --port COM2 --loop --wait-command --interval 0.02
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

## Current Prototype Features And Verifiable Requirements

This chapter captures what is currently implemented and what should be
re-verified during future regression checks.

### Enumerated Features

1. CLI capture entry point in `pycollect.py` supports blind mode, matplotlib
  mode, and Qt GUI mode.
2. DRC monitor simulator in `drc_monitor_simulator.py` replays DRC records as
  framed serial data with escape handling compatible with monitor-style
  transport (`0x7E` flag framing, `0x7D` escaping).
3. Qt GUI (`pycollect_qt_gui.py`) supports autostart capture when port is
  provided from CLI.
4. Output naming supports user-provided base name via `--output` while keeping
  timestamp suffix in saved DRC filename.
5. Trend and waveform configuration is loaded from a single JSON file
  (`pycollect_gui_config.json`).
6. Trend channel metadata (label, unit, divider, subgroup, value index) is
  loaded from `params5.txt` row identifiers selected in JSON.
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

### Enumerated Requirements For Future Verification

1. `python pycollect.py --help` must list `--output` and
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

