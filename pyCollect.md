# pyCollect User Manual (GUI)

Version: 1.0  
Date: 2026-05-28  
Audience: End users operating `pyCollect.exe` (GUI only)

---

## 1. Purpose

`pyCollect` is a bedside monitor data collection and review application.

This manual covers the complete GUI workflow:

1. Install from setup executable.
2. Start the application.
3. Configure monitoring session settings.
4. Collect and save a DRC recording.
5. Convert the recording to CSV.
6. Review the recorded session in the GUI.

This document does **not** cover command-line (CLI) operation.

---

## 2. System Requirements

- Windows 10 or Windows 11
- Access to monitor serial data stream (physical monitor or validated simulator path)
- Available COM port
- User permission to install desktop applications

Recommended:

- Local write access to `%LOCALAPPDATA%\pyCollect`
- Local disk space for DRC and CSV outputs

---

## 3. Installation

### 3.1 Install Using Setup EXE

1. Locate `pyCollect_Setup.exe`.
2. Run installer.
3. Accept prompts and complete installation.
4. Optionally allow desktop/start menu shortcut creation.

### 3.2 Installed Components

The installer places application and runtime files in these locations:

- Application: `%ProgramFiles%\pyCollect` (or selected install folder)
- Runtime config and writable data seed: `%LOCALAPPDATA%\pyCollect`
- Default local output folder: `%LOCALAPPDATA%\pyCollect\output`

### 3.3 Uninstall

Uninstall from Windows Apps/Programs as usual.

Note: local runtime data under `%LOCALAPPDATA%\pyCollect` may be removed by uninstall policy.

---

## 4. Launching pyCollect (GUI)

Launch methods:

1. Desktop shortcut: `pyCollect`
2. Start menu: `pyCollect`
3. Executable: `pyCollect.exe`

On launch, the main window title is **pyCollect Interactive Viewer**.

---

## 5. Main Window Layout

The GUI is organized into a left workflow sidebar and right graph area.

### 5.1 Capture Tab

The CAPTURE tab contains all controls for configuring and running a live recording session.

![Capture Tab - Live Recording](C:/Users/100014430/Documents/GitHub/Enterprise/pyCollect/assets/screenshot_capture_tab.png)

### 5.2 Review Tab

The REVIEW tab provides file review, CSV conversion, and capture log summary.

![Review Tab - DRC File Review](C:/Users/100014430/Documents/GitHub/Enterprise/pyCollect/assets/screenshot_review_tab.png)

### 5.3 Sidebar Sections

The sidebar uses a tabbed interface with **CAPTURE** and **REVIEW** tabs:

**CAPTURE tab:**
- `START` / `STOP` button
- `Apply Capture Selection to Live View`
- Source Port (with automatic S/5 port scan)
- Baud rate (successful source+baud combinations are highlighted after scan)
- Refresh Ports / Scanning indicator with scan result tooltip
- Trend Interval
- Recording Folder + Browse
- Recording Filename + Browse
- Record Duration (sec)

**REVIEW tab:**
- `REVIEW` / `Exit Review` buttons
- Review File (Input) + Open browse
- `Convert Current DRC to CSV`
- Generated CSV Files list
- Capture Log summary (duration, PC–Monitor clock offset, record counts)

**Below tabs (always visible):**
- `Screen Setup` (collapsible)
  - Vitals Window (sec)
  - Waveform Window (sec)
- `Waveform Selection` (collapsible)
- `Trends Selection` (collapsible)
- `Recorder Output` (status log)
- `Advanced` (lock, simulator speed)

### 5.4 Graph/Status Area

- Live trend and waveform plots
- Header with:
  - Last record timestamp
  - Elapsed header time
  - Recently active waveforms
  - Recent alarm text
- Review slider (visible in review mode)

---

## 6. Quick Start (Typical Collection Session)

1. Launch `pyCollect`.
2. In `Monitor Connection`:
   - Select correct COM port.
   - Select baud rate (`19200` for many real monitor sessions, `115200` for many simulator/bridged sessions).
4. In `File Save Status`:
   - Choose Save Folder.
   - Enter Save Filename (example: `record.drc`).
4. In `Session Setup`:
   - Set Record Duration.
   - Set trend/wave display windows.
5. In `Waveform Selection` and `Trends Selection`:
   - Select desired channels.
6. Click `START`.
7. Observe live status in `Recorder Output` and plots.
8. Click `STOP` when finished (or wait for duration to complete).
9. Confirm file state indicates closed/ready.
10. Click `Convert Current DRC to CSV`.
11. Click `REVIEW` to inspect the captured recording in GUI review mode.

---

## 7. Data Collection Procedure (Detailed)

### 7.1 Configure Connection

1. Open `Monitor Connection`.
2. Click `Refresh Ports`.
3. Select active source COM port.
4. Set baud rate.
5. Optionally set Trend Interval.

### 7.2 Configure Output File

1. Open `File Save Status`.
2. Set `Save Folder` (use `Browse...` if needed).
3. Set `Save Filename`.
4. Confirm save folder and filename are correct.

Behavior note:

- If the target filename already exists, pyCollect automatically switches to a timestamped non-overwriting filename and logs this action.

### 7.3 Set Session Duration and Display Windows

1. Open `Session Setup`.
2. Set `Record Duration (sec)`.
3. Set `Vitals Window (sec)` and `Waveform Window (sec)`.

### 7.4 Select Channels

1. Open `Waveform Selection` to choose waveform channels.
2. Open `Trends Selection` to choose trend channels.
3. Use filter boxes to quickly find channels.

### 7.5 Start Recording

1. Click `START`.
2. Verify messages in `Recorder Output` such as connection and package progress.
3. Confirm plots update with incoming data.

### 7.6 Stop Recording

1. Click `STOP` (or let duration complete).
2. Wait for stop command completion and file close confirmation in log.
3. Confirm `Current DRC File` is populated and ready.

---

## 8. CSV Conversion Procedure (GUI)

After a recording is complete:

1. Go to `File Save Status`.
2. Click `Convert Current DRC to CSV`.
3. Wait for progress (% shown on button).
4. On completion, review `Saved CSV Files` list.

Expected outputs (same folder as the DRC file):

- `*_trends.csv` (always generated)
- `*_waves.csv` (generated when waveform samples are available)
- `*_pacers.csv` (generated when pacer data is available)
- `*_alarms.csv` (generated when alarm records are available)

---

## 9. Review Procedure (GUI)

Review mode replays the current recorded DRC file inside the GUI.

1. Ensure capture is not running.
2. Ensure `Current DRC File` exists.
3. Click `REVIEW`.
4. Use the review slider to move through recorded record positions.
5. Observe trend/wave plots and header timing/alarm indicators.

Review mode notes:

- `REVIEW` operates on the **current DRC file** tracked in `File Save Status`.
- Review slider appears only while review mode is active.
- Opening a review file does not change capture output settings.

---

## 10. Color/Status Behavior (Operator Reference)

### 10.1 Main Capture Button

- Blue `START`: idle/ready
- Green `START`: armed state
- Red `STOP`: recording active

### 10.2 File Save State (Current DRC File)

- Blue: appending/writing during capture
- Green: closed and ready for conversion/review

### 10.3 Waveform Selection Status (catalog colors)

In simulation-oriented sessions:

- Green: selected and receiving data
- Blue: receiving data but not selected
- Yellow: selected but waiting for data

In other sessions, delayed/missing states may display warning/alarm colors.

---

## 11. Runtime Configuration Persistence

pyCollect persists runtime settings in local config so next launch can reuse prior values.

Persisted examples include:

- Selected baud rate
- Duration/window settings
- Selected trends and waveforms
- Output folder and filename
- Section lock states

Primary runtime config location:

- `%LOCALAPPDATA%\pyCollect\pycollect_gui_config.json`

---

## 12. Logs and Output Files

### 12.1 Recording Output

- DRC file: as configured in `File Save Status`
- Capture log file: saved when capture closes (written alongside DRC output path)

### 12.2 GUI Status Log

- Visible in `Recorder Output` panel during runtime

### 12.3 Startup Log

- `output\pycollect_qt_gui_startup.log` in application/runtime working context

---

## 13. Troubleshooting

### 13.1 No COM Ports Visible

- Click `Refresh Ports`.
- Verify cable/adapter and driver installation.
- Verify port is not already opened by another app.

### 13.2 Cannot Start Capture

- Confirm a COM port is selected.
- Confirm output folder is writable.
- Check `Recorder Output` for specific error text.

If scanning shows green-highlighted source+baud combinations, prefer those first.

### 13.3 Flat or Missing Waveforms

- Verify correct source and baud rate.
- Check channel selection in `Waveform Selection`.
- Allow a few seconds for incoming packets and state transition.

Note: a zero-waveform capture configuration is valid; trend/alarm capture can run without waveform rows.

### 13.4 CSV Conversion Disabled

Conversion is enabled only when:

- capture has completed,
- current DRC file exists,
- conversion is not already running.

### 13.5 REVIEW Disabled

Review is enabled only when:

- capture is stopped,
- current DRC file exists and is closed.

---

## 14. Operational Notes

- Use consistent naming for each recording session (patient/case/date policy as defined by your site).
- Verify clock/timestamp consistency across systems when reviewing time-based events.
- Keep monitor source, COM mapping, and baud settings documented for repeatability.

---

## 15. Clinical Use Disclaimer

For research/engineering workflow support only unless explicitly validated and approved by your organization for clinical use.
