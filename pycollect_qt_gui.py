import argparse
import json
import math
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
import serial
from PyQt5 import QtCore, QtWidgets
from serial.tools import list_ports

import pycollect


START_PARAM_HEX = (
    "7E31 0000 00E8 FD25 0407 6700 0000 0000 0000 0000 "
    "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
    "0001 0A00 0800 0000 0000 BF7E"
)
STOP_PARAM_HEX = (
    "7E31 0000 00E8 FD33 0607 6700 0000 0000 0000 0000 "
    "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
    "0001 0000 0800 0000 0000 C57E"
)
START_WAVES_HEX = (
    "7E58 0000 00E8 FD58 2708 6700 0000 0001 0000 0000 "
    "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
    "0000 0005 0001 0408 09FF 0000 0000 0000 0000 0000 "
    "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
    "0000 0000 0000 0000 0000 0045 7E"
)
STOP_WAVES_HEX = (
    "7E58 0000 00E8 FD35 2808 6700 0000 0001 0000 0000 "
    "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
    "0001 0005 0001 FF00 0000 0000 0000 0000 0000 0000 "
    "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
    "0000 0000 0000 0000 0000 000F 7E"
)

DEFAULT_CONFIG = "pycollect_gui_config.json"


class SignalConfigError(Exception):
    pass


def _safe_divider(value):
    try:
        parsed = float(value)
    except Exception:
        return 1.0
    if parsed == 0.0:
        return 1.0
    return parsed


def _read_tab_rows(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        rows.append(text.split("\t"))
    return rows


def _display_name(label, unit):
    clean_label = (label or "").strip() or "Unknown"
    clean_unit = (unit or "").strip()
    if clean_unit and clean_unit != "-":
        return f"{clean_label} [{clean_unit}]"
    return clean_label


def load_signal_config(base_dir, config_path=None):
    cfg_path = (
        Path(config_path)
        if config_path
        else (base_dir / DEFAULT_CONFIG)
    )
    if not cfg_path.exists():
        raise SignalConfigError(f"Config file not found: {cfg_path}")

    raw_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    params_rel = raw_cfg["signal_sources"]["params_file"]
    waves_rel = raw_cfg["signal_sources"]["waves_file"]
    params_path = (base_dir / params_rel).resolve()
    waves_path = (base_dir / waves_rel).resolve()

    if not params_path.exists():
        raise SignalConfigError(f"params file not found: {params_path}")
    if not waves_path.exists():
        raise SignalConfigError(f"waves file not found: {waves_path}")

    params_rows = _read_tab_rows(params_path)
    waves_rows = _read_tab_rows(waves_path)

    trend_select = raw_cfg["channels"]["trends"]
    wave_select = raw_cfg["channels"]["waves"]

    if len(trend_select) != 4:
        raise SignalConfigError(
            "JSON must declare exactly 4 trend row identifiers"
        )
    if len(wave_select) != 4:
        raise SignalConfigError(
            "JSON must declare exactly 4 waveform row identifiers"
        )

    all_trend_defs = []
    for row_id, row in enumerate(params_rows, start=1):
        if len(row) < 7:
            continue
        subgroup = int(row[1])
        value_index = int(row[2])
        divider = _safe_divider(row[3])
        short_label = row[4].strip()
        unit = row[5].strip()
        all_trend_defs.append(
            {
                "row_identifier": row_id,
                "subgroup": subgroup,
                "value_index": value_index,
                "divider": divider,
                "label": short_label,
                "unit": unit,
                "title": _display_name(short_label, unit),
            }
        )

    all_wave_defs = []
    for row_id, row in enumerate(waves_rows, start=1):
        if len(row) < 8:
            continue
        sample_hz = float(row[1])
        divider = _safe_divider(row[3])
        short_label = row[5].strip()
        unit = row[6].strip()
        all_wave_defs.append(
            {
                "row_identifier": row_id,
                "sr_type": row_id,
                "sample_hz": max(1.0, sample_hz),
                "divider": divider,
                "label": short_label,
                "unit": unit,
                "title": _display_name(short_label, unit),
            }
        )

    trend_by_row = {
        item["row_identifier"]: item
        for item in all_trend_defs
    }
    wave_by_row = {
        item["row_identifier"]: item
        for item in all_wave_defs
    }

    trend_defs = []
    for idx, item in enumerate(trend_select):
        row_id = int(item["row_identifier"])
        if row_id not in trend_by_row:
            raise SignalConfigError(
                f"Trend row_identifier out of range: {row_id}"
            )
        selected = dict(trend_by_row[row_id])
        selected["id"] = f"trend{idx + 1}"
        trend_defs.append(selected)

    wave_defs = []
    for idx, item in enumerate(wave_select):
        row_id = int(item["row_identifier"])
        if row_id not in wave_by_row:
            raise SignalConfigError(
                f"Wave row_identifier out of range: {row_id}"
            )
        selected = dict(wave_by_row[row_id])
        selected["id"] = f"wave{idx + 1}"
        wave_defs.append(selected)

    ui_cfg = raw_cfg.get("ui", {})
    initial_duration = int(ui_cfg.get("duration_sec", 60))
    initial_trend_window = float(ui_cfg.get("trend_window_sec", 60))
    initial_wave_window = float(ui_cfg.get("wave_window_sec", 10))

    return {
        "path": str(cfg_path),
        "all_trend_defs": all_trend_defs,
        "all_wave_defs": all_wave_defs,
        "trend_defs": trend_defs,
        "wave_defs": wave_defs,
        "initial_duration": max(5, initial_duration),
        "initial_trend_window": max(10.0, initial_trend_window),
        "initial_wave_window": max(10.0, initial_wave_window),
    }


class CollapsibleSection(QtWidgets.QWidget):
    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        self.toggle_btn = QtWidgets.QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow
        )

        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 6, 8, 6)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.toggle_btn)
        root.addWidget(self.content)

        self.toggle_btn.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        self.content.setVisible(checked)
        self.toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )


class CollectorWorker(QtCore.QThread):
    package_signal = QtCore.pyqtSignal(object)
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(
        self,
        port,
        duration_sec,
        all_trend_defs,
        all_wave_defs,
        trend_defs,
        wave_defs,
        output_name="",
        parent=None,
    ):
        super().__init__(parent)
        self.port = port
        self.duration_sec = duration_sec
        self.all_trend_defs = all_trend_defs
        self.all_wave_defs = all_wave_defs
        self.trend_defs = trend_defs
        self.wave_defs = wave_defs
        self.output_name = output_name
        self._stop_requested = False
        self.all_wave_by_type = {
            item["sr_type"]: item
            for item in all_wave_defs
        }
        self.selected_wave_types = {
            item["sr_type"]: item["id"]
            for item in wave_defs
        }
        self.selected_wave_ids = [item["id"] for item in wave_defs]

    def request_stop(self):
        self._stop_requested = True

    def _send(self, ser, hex_command):
        ser.write(bytes.fromhex(pycollect.stripspaces(hex_command)))

    def _extract_trends(self, payload):
        out = {}
        all_values = {}
        subgroup_values = {}
        positive_rows = set()

        for offset, sr_type in zip(
            payload["raw_offsets"],
            payload["sr_types"],
        ):
            if sr_type <= 0:
                continue
            start = offset
            end = start + 279
            if start < 0 or end > len(payload["bytes"]):
                continue

            trend_data = payload["bytes"][start:end]
            if len(trend_data) < 278:
                continue

            subgroup = trend_data[277] & 0x1F
            values_raw = trend_data[4:274]
            values = [
                int.from_bytes(
                    values_raw[idx:idx + 2],
                    byteorder="little",
                    signed=True,
                )
                for idx in range(0, len(values_raw), 2)
            ]
            subgroup_values[subgroup] = values

        for item in self.all_trend_defs:
            values = subgroup_values.get(item["subgroup"])
            if values is None:
                continue
            idx = item["value_index"]
            if idx < 0 or idx >= len(values):
                continue
            raw_value = values[idx]
            if raw_value == pycollect.DATA_INVALID:
                continue
            scaled = float(raw_value) / item["divider"]
            all_values[item["row_identifier"]] = scaled
            if scaled > 0:
                positive_rows.add(item["row_identifier"])

        for item in self.trend_defs:
            values = subgroup_values.get(item["subgroup"])
            if values is None:
                continue
            if item["value_index"] < 0 or item["value_index"] >= len(values):
                continue

            raw_value = values[item["value_index"]]
            if raw_value == pycollect.DATA_INVALID:
                continue

            out[item["id"]] = float(raw_value) / item["divider"]

        return out, positive_rows, all_values

    def _extract_waves(self, payload):
        out = {}
        positive_rows = set()
        valid_indices = [
            idx
            for idx, item in enumerate(payload["sr_types"])
            if item > 0
        ]

        for pos, idx in enumerate(valid_indices):
            sr_type = payload["sr_types"][idx]
            chan_id = self.selected_wave_types.get(sr_type)
            if not chan_id or chan_id in out:
                continue

            start = payload["raw_offsets"][idx] + 6
            if pos < len(valid_indices) - 1:
                end = payload["raw_offsets"][valid_indices[pos + 1]]
            else:
                end = len(payload["bytes"])

            if not (0 <= start < end <= len(payload["bytes"])):
                continue

            wave_bytes = payload["bytes"][start:end]
            if len(wave_bytes) < 2:
                continue

            sample_count = len(wave_bytes) // 2
            unpack_fmt = "<" + "h" * sample_count
            raw_samples = pycollect.struct.unpack(
                unpack_fmt,
                wave_bytes[:sample_count * 2],
            )

            wave_meta = self.all_wave_by_type.get(sr_type)
            divider = 1.0
            if wave_meta is not None:
                divider = wave_meta["divider"]
            scaled_samples = [
                float(sample) / divider
                for sample in raw_samples
            ]

            if (
                wave_meta is not None
                and any(sample > 0 for sample in scaled_samples)
            ):
                positive_rows.add(wave_meta["row_identifier"])

            if chan_id and chan_id not in out:
                out[chan_id] = scaled_samples

        return out, positive_rows

    def _extract_from_record(self, record_data):
        if len(record_data) < 40:
            return {
                "trends": {},
                "trend_rows": {},
                "waves": {},
                "positive_trend_rows": [],
                "positive_wave_rows": [],
            }

        header_fmt = "< h b b H I b b H h " + "h b" * pycollect.DRI_MAX_SUBRECS
        header_struct = pycollect.struct.Struct(header_fmt)

        try:
            header = header_struct.unpack(record_data[:40])
        except Exception:
            return {
                "trends": {},
                "trend_rows": {},
                "waves": {},
                "positive_trend_rows": [],
                "positive_wave_rows": [],
            }

        r_len = header[0]
        r_maintype = header[8]
        if r_len < 40 or r_len > len(record_data):
            return {
                "trends": {},
                "trend_rows": {},
                "waves": {},
                "positive_trend_rows": [],
                "positive_wave_rows": [],
            }

        sr_desc = header[9:]
        raw_offsets = sr_desc[::2]
        raw_types = sr_desc[1::2]
        sr_types = [
            0 if item < -1 or item > 50 else item
            for item in raw_types
        ]
        payload = record_data[40:r_len]

        parsed = {
            "bytes": payload,
            "raw_offsets": raw_offsets,
            "sr_types": sr_types,
        }

        if r_maintype == 0:
            trends, positive_trend_rows, all_trend_rows = (
                self._extract_trends(parsed)
            )
            return {
                "trends": trends,
                "trend_rows": all_trend_rows,
                "waves": {},
                "positive_trend_rows": list(positive_trend_rows),
                "positive_wave_rows": [],
            }
        if r_maintype == 1:
            waves, positive_wave_rows = self._extract_waves(parsed)
            return {
                "trends": {},
                "trend_rows": {},
                "waves": waves,
                "positive_trend_rows": [],
                "positive_wave_rows": list(positive_wave_rows),
            }
        return {
            "trends": {},
            "trend_rows": {},
            "waves": {},
            "positive_trend_rows": [],
            "positive_wave_rows": [],
        }

    def run(self):
        ser = None
        output_file = ""
        output_fp = None
        logical_time_sec = 0.0
        try:
            output_file = pycollect.build_output_filename(self.output_name)
            output_fp = open(output_file, "wb")

            ser = serial.Serial(
                port=self.port,
                baudrate=115200,
                timeout=5,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                rtscts=True,
            )

            self.status_signal.emit(f"Connected to {self.port}")
            self._send(ser, START_PARAM_HEX)
            self._send(ser, START_WAVES_HEX)
            self.status_signal.emit("Capture started")

            for idx in range(self.duration_sec):
                if self._stop_requested:
                    self.status_signal.emit("Stop requested")
                    break

                incoming_data = ser.read_until(bytes([pycollect.FLAG_CHAR]))
                if len(incoming_data) < 40:
                    incoming_data = ser.read_until(
                        bytes([pycollect.FLAG_CHAR])
                    )

                processed = pycollect.process_received_data(incoming_data)
                logical_time_sec += 1.0
                if len(processed) > 40:
                    output_fp.write(processed)
                    output_fp.flush()
                    payload = self._extract_from_record(processed)
                    payload["index"] = idx + 1
                    payload["length"] = len(processed)
                    payload["time"] = logical_time_sec
                    self.package_signal.emit(payload)
                    self.status_signal.emit(
                        f"Package {idx + 1}/{self.duration_sec}, "
                        f"{len(processed)} bytes"
                    )
                else:
                    self.status_signal.emit(f"Package {idx + 1} discarded")

                time.sleep(1)

            self._send(ser, STOP_PARAM_HEX)
            self._send(ser, STOP_WAVES_HEX)
            self.status_signal.emit("Stop commands sent")

            self.finished_signal.emit(output_file)
        except Exception as exc:
            self.error_signal.emit(str(exc))
        finally:
            if output_fp is not None and not output_fp.closed:
                output_fp.close()
            if ser is not None and ser.is_open:
                ser.close()


class PyCollectQtWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        config,
        output_name="",
        initial_port=None,
        autostart=False,
        simulation_mode=False,
        initial_duration=None,
        debug_stdout=False,
    ):
        super().__init__()
        self.setWindowTitle("pyCollect Interactive Viewer")
        self.resize(1300, 760)

        self.config = config
        self.all_trend_defs = config["all_trend_defs"]
        self.all_wave_defs = config["all_wave_defs"]
        self.output_name = output_name
        self.autostart = autostart
        self.simulation_mode = simulation_mode
        self.debug_stdout = debug_stdout
        self._is_closing = False
        self.trend_defs = config["trend_defs"]
        self.wave_defs = config["wave_defs"]
        self.positive_trend_rows = set()
        self.positive_wave_rows = set()

        # Waveform request catalog state.
        # wave_requested_rows: rows the user explicitly asked for.
        # wave_last_received_at: monotonic time of last sample per row.
        self.wave_requested_rows = set()
        self.wave_last_received_at = {}
        self.wave_request_buttons = {}
        self.WAVE_REQUEST_TIMEOUT_SEC = 5.0

        self.worker = None
        self.logical_now_sec = 0.0
        self._in_splitter_adjust = False

        self.trend_buffers = {item["id"]: deque() for item in self.trend_defs}
        self.trend_history_by_row = {}
        self.wave_buffers = {item["id"]: deque() for item in self.wave_defs}
        self.wave_cursors = {item["id"]: None for item in self.wave_defs}

        self.trend_plots = {}
        self.trend_curves = {}
        self.wave_plots = {}
        self.wave_curves = {}
        self.slot_buttons = {}
        self.selector_popups = {}
        self._trend_selector_slot_idx = None
        self.selector_filter_dirty = {
            "trend": True,
            "wave": True,
        }

        self.sim_idle_timer = QtCore.QTimer(self)
        self.sim_idle_timer.setSingleShot(True)
        self.sim_idle_timer.setInterval(10000)
        self.sim_idle_timer.timeout.connect(self._on_simulation_idle_timeout)

        self.wave_request_state_timer = QtCore.QTimer(self)
        self.wave_request_state_timer.setInterval(1000)
        self.wave_request_state_timer.timeout.connect(
            self._refresh_wave_request_button_states
        )

        self._apply_pcs_theme()
        self._build_ui()
        self._connect_signals()
        self.refresh_ports()

        if initial_duration is not None:
            self.duration_spin.setValue(initial_duration)

        if initial_port:
            port_index = self.port_combo.findText(initial_port)
            if port_index >= 0:
                self.port_combo.setCurrentIndex(port_index)
                self.log(f"Preselected port from CLI: {initial_port}")
            else:
                self.log(f"CLI port not found: {initial_port}")

        if self.simulation_mode and self.autostart:
            self.conn_section.toggle_btn.setChecked(False)
            self.capture_section.toggle_btn.setChecked(False)

        if autostart and initial_port:
            QtCore.QTimer.singleShot(0, self.start_capture)

        # Start the wave catalog color refresh loop now so colors update
        # before, during, and after capture (1 Hz).
        self.wave_request_state_timer.start()
        # Seed: displayed rows are auto-requested at startup.
        for row_id in self._displayed_wave_row_ids():
            self.wave_requested_rows.add(int(row_id))
        self._refresh_wave_request_button_states()

    def _apply_pcs_theme(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #d6dde6;
                color: #111111;
                font-size: 12px;
            }
            QFrame {
                background: #d3dae3;
                border: 1px solid #b8c0cb;
            }
            QLabel {
                color: #111111;
            }
            QToolButton {
                background: #c7ced8;
                border: 1px solid #a9b2be;
                border-radius: 3px;
                font-weight: 600;
                padding: 6px;
                text-align: left;
            }
            QToolButton:hover {
                background: #bec7d2;
            }
            QComboBox, QSpinBox, QDoubleSpinBox, QPushButton {
                background: #f1f4f7;
                border: 1px solid #9aa5b3;
                border-radius: 3px;
                padding: 4px;
            }
            QPlainTextEdit {
                background: #eef2f6;
                border: 1px solid #9aa5b3;
            }
            QSplitter::handle {
                background: #98a4b4;
                width: 6px;
            }
            """
        )
        pg.setConfigOption("background", "#edf1f5")
        pg.setConfigOption("foreground", "#111111")

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setMinimumWidth(330)
        self.sidebar.setMaximumWidth(380)
        self.sidebar.setFrameShape(QtWidgets.QFrame.StyledPanel)
        left = QtWidgets.QVBoxLayout(self.sidebar)
        left.setContentsMargins(10, 10, 10, 10)
        left.setSpacing(8)

        title = QtWidgets.QLabel("Capture Control")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        left.addWidget(title)

        self.conn_section = CollapsibleSection("Connection", expanded=True)
        left.addWidget(self.conn_section)
        self.port_combo = QtWidgets.QComboBox()
        self.refresh_ports_btn = QtWidgets.QPushButton("Refresh Ports")
        self.conn_section.content_layout.addWidget(
            QtWidgets.QLabel("Serial Port")
        )
        self.conn_section.content_layout.addWidget(self.port_combo)
        self.conn_section.content_layout.addWidget(self.refresh_ports_btn)

        view_section = CollapsibleSection("Display Windows", expanded=True)
        left.addWidget(view_section)

        self.duration_spin = QtWidgets.QSpinBox()
        self.duration_spin.setRange(5, 3600)
        self.duration_spin.setValue(self.config["initial_duration"])
        view_section.content_layout.addWidget(
            QtWidgets.QLabel("Duration (sec)")
        )
        view_section.content_layout.addWidget(self.duration_spin)

        self.hr_window_spin = QtWidgets.QSpinBox()
        self.hr_window_spin.setRange(10, 3600)
        self.hr_window_spin.setValue(int(self.config["initial_trend_window"]))
        view_section.content_layout.addWidget(
            QtWidgets.QLabel("Trend Time Length (sec)")
        )
        view_section.content_layout.addWidget(self.hr_window_spin)

        self.ecg_window_spin = QtWidgets.QDoubleSpinBox()
        self.ecg_window_spin.setRange(10.0, 300.0)
        self.ecg_window_spin.setSingleStep(0.5)
        self.ecg_window_spin.setValue(self.config["initial_wave_window"])
        view_section.content_layout.addWidget(
            QtWidgets.QLabel("Wave Time Length (sec, 10..300)")
        )
        view_section.content_layout.addWidget(self.ecg_window_spin)

        self.capture_section = CollapsibleSection("Capture", expanded=True)
        left.addWidget(self.capture_section)
        self.start_btn = QtWidgets.QPushButton("Start Capture")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.capture_section.content_layout.addWidget(self.start_btn)
        self.capture_section.content_layout.addWidget(self.stop_btn)

        signal_section = CollapsibleSection("Signal Selection", expanded=True)
        left.addWidget(signal_section)
        selector_grid = QtWidgets.QGridLayout()
        selector_grid.setContentsMargins(0, 0, 0, 0)
        selector_grid.setHorizontalSpacing(6)
        selector_grid.setVerticalSpacing(6)
        signal_section.content_layout.addLayout(selector_grid)

        for row in range(4):
            trend_btn = QtWidgets.QPushButton()
            wave_btn = QtWidgets.QPushButton()
            trend_slot = f"trend{row + 1}"
            wave_slot = f"wave{row + 1}"
            self.slot_buttons[trend_slot] = trend_btn
            self.slot_buttons[wave_slot] = wave_btn
            selector_grid.addWidget(trend_btn, row, 0)
            selector_grid.addWidget(wave_btn, row, 1)
            trend_btn.clicked.connect(
                lambda _checked=False, idx=row: self.open_slot_selector(
                    "trend",
                    idx,
                )
            )
            wave_btn.clicked.connect(
                lambda _checked=False, idx=row: self.open_slot_selector(
                    "wave",
                    idx,
                )
            )

        status_section = CollapsibleSection("Status", expanded=True)
        left.addWidget(status_section)
        self.status_box = QtWidgets.QPlainTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumBlockCount(500)
        status_section.content_layout.addWidget(self.status_box)

        # Waveform Request Catalog: full list of available waveforms.
        # Buttons are color-coded by state machine; see
        # _wave_request_button_state() for transitions. Displayed rows are
        # auto-requested and protected from being unrequested.
        self.wave_catalog_section = CollapsibleSection(
            "Waveform Request Catalog",
            expanded=False,
        )
        left.insertWidget(
            left.indexOf(view_section),
            self.wave_catalog_section,
        )
        catalog_scroll = QtWidgets.QScrollArea()
        catalog_scroll.setWidgetResizable(True)
        catalog_scroll.setMinimumHeight(120)
        catalog_scroll.setMaximumHeight(220)
        catalog_inner = QtWidgets.QWidget()
        catalog_grid = QtWidgets.QGridLayout(catalog_inner)
        catalog_grid.setContentsMargins(0, 0, 0, 0)
        catalog_grid.setHorizontalSpacing(4)
        catalog_grid.setVerticalSpacing(4)

        cols = 2
        for idx, item in enumerate(self.all_wave_defs):
            row_id = int(item["row_identifier"])
            label = item.get("label") or item.get("title") or ""
            btn = QtWidgets.QPushButton(f"#{row_id} {label}")
            btn.setCheckable(True)
            btn.setMinimumWidth(140)
            btn.setProperty("row_id", row_id)
            btn.toggled.connect(
                lambda checked, rid=row_id: self._on_wave_request_clicked(
                    rid,
                    checked,
                )
            )
            self.wave_request_buttons[row_id] = btn
            catalog_grid.addWidget(btn, idx // cols, idx % cols)

        catalog_scroll.setWidget(catalog_inner)
        self.wave_catalog_section.content_layout.addWidget(catalog_scroll)

        left.addStretch(1)
        layout.addWidget(self.sidebar)

        self.graph_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.graph_splitter.setChildrenCollapsible(False)

        self.trends_panel = QtWidgets.QWidget()
        trends_layout = QtWidgets.QVBoxLayout(self.trends_panel)
        trends_layout.setContentsMargins(0, 0, 0, 0)
        trends_layout.setSpacing(8)

        trend_colors = ["#2b83f6", "#24b47e", "#b38ddb", "#6fd3ff"]
        for idx, item in enumerate(self.trend_defs):
            plot = pg.PlotWidget(title=item["title"])
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.setLabel("left", text=item["label"], units=item["unit"])
            curve = plot.plot(
                pen=pg.mkPen(
                    trend_colors[idx % len(trend_colors)],
                    width=2,
                )
            )
            self.trend_plots[item["id"]] = plot
            self.trend_curves[item["id"]] = curve
            trends_layout.addWidget(plot, 1)

        self.waves_panel = QtWidgets.QWidget()
        waves_layout = QtWidgets.QVBoxLayout(self.waves_panel)
        waves_layout.setContentsMargins(0, 0, 0, 0)
        waves_layout.setSpacing(8)

        wave_colors = ["#f23c3c", "#ff8c42", "#ff5a7a", "#f6d743"]
        for idx, item in enumerate(self.wave_defs):
            plot = pg.PlotWidget(title=item["title"])
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.setLabel("left", text=item["label"], units=item["unit"])
            curve = plot.plot(
                pen=pg.mkPen(
                    wave_colors[idx % len(wave_colors)],
                    width=1.5,
                )
            )
            self.wave_plots[item["id"]] = plot
            self.wave_curves[item["id"]] = curve
            waves_layout.addWidget(plot, 1)

        self.graph_splitter.addWidget(self.trends_panel)
        self.graph_splitter.addWidget(self.waves_panel)
        self.graph_splitter.setStretchFactor(0, 1)
        self.graph_splitter.setStretchFactor(1, 1)
        self.graph_splitter.setSizes([500, 500])

        layout.addWidget(self.graph_splitter, 1)
        self.refresh_slot_buttons()
        self._prepare_selector_popups()

    def _connect_signals(self):
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        self.start_btn.clicked.connect(self.start_capture)
        self.stop_btn.clicked.connect(self.stop_capture)
        self.hr_window_spin.valueChanged.connect(self.update_plots)
        self.ecg_window_spin.valueChanged.connect(self.update_plots)
        self.graph_splitter.splitterMoved.connect(self.on_splitter_moved)

    @staticmethod
    def _slot_label(prefix, item):
        return f"{prefix}: {item['label']} [{item['unit']}]"

    def refresh_slot_buttons(self):
        for idx, item in enumerate(self.trend_defs):
            slot = f"trend{idx + 1}"
            self.slot_buttons[slot].setText(self._slot_label("T", item))
        for idx, item in enumerate(self.wave_defs):
            slot = f"wave{idx + 1}"
            self.slot_buttons[slot].setText(self._slot_label("W", item))

    def _prepare_selector_popups(self):
        self.selector_popups["trend"] = self._build_trend_grid_popup()
        self.selector_popups["wave"] = self._build_selector_popup("wave")

    def _build_trend_grid_popup(self):
        popup = QtWidgets.QDialog(self)
        popup.setWindowTitle("Select Trend Parameter")
        popup.resize(760, 520)
        layout = QtWidgets.QVBoxLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        positive_only = QtWidgets.QCheckBox("Select only positive")
        positive_only.setChecked(True)
        layout.addWidget(positive_only)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)

        container = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)

        columns = 5
        total = len(self.all_trend_defs)
        rows = max(1, int(math.ceil(float(total) / float(columns))))
        trend_buttons = []
        for idx, item in enumerate(self.all_trend_defs):
            row = idx % rows
            col = idx // rows
            btn = QtWidgets.QPushButton(item["label"])
            btn.setToolTip(
                f"Row {item['row_identifier']} | "
                f"{item['label']} [{item['unit']}]"
            )
            btn.clicked.connect(
                lambda _checked=False, selected=dict(item):
                self._on_trend_grid_pick(selected)
            )
            trend_buttons.append(
                {
                    "button": btn,
                    "row_identifier": int(item["row_identifier"]),
                }
            )
            grid.addWidget(btn, row, col)

        scroll.setWidget(container)
        positive_only.toggled.connect(
            lambda _checked=False: self._apply_selector_filter(
                "trend",
                force=True,
            )
        )

        return {
            "dialog": popup,
            "positive_only": positive_only,
            "trend_buttons": trend_buttons,
        }

    def _on_trend_grid_pick(self, item):
        if self._trend_selector_slot_idx is None:
            return
        self._apply_slot_selection(
            "trend",
            self._trend_selector_slot_idx,
            item,
        )
        self._trend_selector_slot_idx = None
        self.selector_popups["trend"]["dialog"].accept()

    def _build_selector_popup(self, category):
        popup = QtWidgets.QDialog(self, QtCore.Qt.Popup)
        popup.setWindowTitle("Select Signal")
        popup.setMinimumSize(760, 360)
        layout = QtWidgets.QVBoxLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        positive_only = QtWidgets.QCheckBox("Only rows with positive data")
        positive_only.setChecked(True)
        layout.addWidget(positive_only)

        table = QtWidgets.QTableWidget()
        table.setColumnCount(6)
        if category == "trend":
            table.setHorizontalHeaderLabels(
                ["Row", "Label", "Unit", "Divider", "Subgroup", "Index"]
            )
            defs = self.all_trend_defs
        else:
            table.setHorizontalHeaderLabels(
                ["Row", "Label", "Unit", "Divider", "SampleHz", "Type"]
            )
            defs = self.all_wave_defs

        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(table, 1)

        for row_idx, item in enumerate(defs):
            table.insertRow(row_idx)
            cells = [
                str(item["row_identifier"]),
                item["label"],
                item["unit"],
                f"{item['divider']}",
            ]
            if category == "trend":
                cells.extend(
                    [
                        str(item["subgroup"]),
                        str(item["value_index"]),
                    ]
                )
            else:
                cells.extend(
                    [
                        f"{item['sample_hz']:.1f}",
                        str(item["sr_type"]),
                    ]
                )

            for col, value in enumerate(cells):
                table.setItem(row_idx, col, QtWidgets.QTableWidgetItem(value))
            table.item(row_idx, 0).setData(QtCore.Qt.UserRole, item)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        choose_btn = QtWidgets.QPushButton("Choose")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        buttons.addWidget(choose_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        positive_only.toggled.connect(
            lambda _checked=False, cat=category:
            self._apply_selector_filter(cat, force=True)
        )
        table.itemDoubleClicked.connect(
            lambda _item, cat=category: self._selector_accept(cat)
        )
        choose_btn.clicked.connect(
            lambda _checked=False, cat=category: self._selector_accept(cat)
        )
        cancel_btn.clicked.connect(popup.reject)

        return {
            "dialog": popup,
            "table": table,
            "positive_only": positive_only,
        }

    def _apply_selector_filter(self, category, force=False):
        state = self.selector_popups[category]
        if category == "trend" and "table" not in state:
            use_positive = state["positive_only"].isChecked()
            if (
                not force
                and use_positive
                and not self.selector_filter_dirty[category]
            ):
                return

            positive_rows = self.positive_trend_rows
            for entry in state["trend_buttons"]:
                row_id = entry["row_identifier"]
                visible = True
                if use_positive:
                    visible = row_id in positive_rows
                entry["button"].setVisible(visible)

            if use_positive:
                self.selector_filter_dirty[category] = False
            return

        table = state["table"]
        use_positive = state["positive_only"].isChecked()

        if (
            not force
            and use_positive
            and not self.selector_filter_dirty[category]
        ):
            return

        positive_rows = (
            self.positive_trend_rows
            if category == "trend"
            else self.positive_wave_rows
        )

        table.setUpdatesEnabled(False)
        first_visible = -1
        for row in range(table.rowCount()):
            cell = table.item(row, 0)
            item = cell.data(QtCore.Qt.UserRole)
            visible = True
            if use_positive:
                visible = item["row_identifier"] in positive_rows
            table.setRowHidden(row, not visible)
            if visible and first_visible < 0:
                first_visible = row

        if first_visible >= 0:
            table.selectRow(first_visible)
        table.setUpdatesEnabled(True)

        if use_positive:
            self.selector_filter_dirty[category] = False

    def _selector_accept(self, category):
        state = self.selector_popups[category]
        table = state["table"]
        row = table.currentRow()
        if row < 0:
            return
        if table.isRowHidden(row):
            return
        state["dialog"].accept()

    def _apply_slot_selection(self, category, slot_idx, new_item):
        if category == "trend":
            slot_id = f"trend{slot_idx + 1}"
            selected = dict(new_item)
            selected["id"] = slot_id
            self.trend_defs[slot_idx] = selected
            self._sync_trend_slot_buffer(slot_idx)
            plot = self.trend_plots[slot_id]
        else:
            slot_id = f"wave{slot_idx + 1}"
            selected = dict(new_item)
            selected["id"] = slot_id
            self.wave_defs[slot_idx] = selected
            self.wave_buffers[slot_id].clear()
            self.wave_cursors[slot_id] = None
            plot = self.wave_plots[slot_id]

        plot.setTitle(selected["title"])
        plot.setLabel("left", text=selected["label"], units=selected["unit"])
        self.refresh_slot_buttons()
        if category == "trend":
            self.update_plots()
        else:
            self.update_plots(force=True)
        self.log(f"Updated {slot_id} to row {selected['row_identifier']}")

    def _sync_trend_slot_buffer(self, slot_idx):
        slot_id = f"trend{slot_idx + 1}"
        row_id = self.trend_defs[slot_idx]["row_identifier"]
        history = self.trend_history_by_row.get(row_id)
        if history is None:
            self.trend_buffers[slot_id].clear()
            return
        self.trend_buffers[slot_id] = deque(history)

    def open_slot_selector(self, category, slot_idx):
        if category == "trend":
            self._trend_selector_slot_idx = slot_idx
            slot_name = f"trend{slot_idx + 1}"
            parent_button = self.slot_buttons[slot_name]
            dialog = self.selector_popups["trend"]["dialog"]
            self._apply_selector_filter("trend", force=False)
            dialog.move(
                parent_button.mapToGlobal(parent_button.rect().bottomLeft())
            )
            dialog.exec_()
            self._trend_selector_slot_idx = None
            return

        if (
            category != "trend"
            and self.worker is not None
            and self.worker.isRunning()
        ):
            self.log("Stop capture before changing signal selections")
            return

        slot_name = f"{category}{slot_idx + 1}"
        parent_button = self.slot_buttons[slot_name]
        state = self.selector_popups[category]

        self._apply_selector_filter(category, force=False)
        state["dialog"].move(
            parent_button.mapToGlobal(parent_button.rect().bottomLeft())
        )

        if state["dialog"].exec_() != QtWidgets.QDialog.Accepted:
            return
        row = state["table"].currentRow()
        if row < 0:
            return
        picked = state["table"].item(row, 0).data(QtCore.Qt.UserRole)
        self._apply_slot_selection(category, slot_idx, picked)

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        if self.debug_stdout:
            try:
                print(line, flush=True)
            except Exception:
                pass
        if self._is_closing:
            return
        try:
            self.status_box.appendPlainText(line)
        except RuntimeError:
            pass

    def refresh_ports(self):
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(sorted(ports))
        if current:
            idx = self.port_combo.findText(current)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)

    def _split_ratios(self):
        sizes = self.graph_splitter.sizes()
        total = max(1, sum(sizes))
        left_ratio = float(sizes[0]) / float(total)
        right_ratio = float(sizes[1]) / float(total)
        return left_ratio, right_ratio, total

    def _effective_windows(self):
        trend_window = max(1.0, float(self.hr_window_spin.value()))
        wave_window = max(1.0, float(self.ecg_window_spin.value()))
        return trend_window, wave_window

    def on_splitter_moved(self, _pos, _index):
        if self._in_splitter_adjust:
            return

        left_ratio, _right_ratio, total = self._split_ratios()
        clamped_ratio = min(0.9, max(0.1, left_ratio))
        if abs(clamped_ratio - left_ratio) > 1e-6:
            self._in_splitter_adjust = True
            left_px = int(total * clamped_ratio)
            right_px = total - left_px
            self.graph_splitter.setSizes([left_px, right_px])
            self._in_splitter_adjust = False

        self.update_plots()

    def start_capture(self):
        port = self.port_combo.currentText().strip()
        if not port:
            self.log("No COM port selected")
            return

        if self.worker is not None and self.worker.isRunning():
            self.log("Capture already running")
            return

        self.logical_now_sec = 0.0
        self.trend_history_by_row.clear()
        for values in self.trend_buffers.values():
            values.clear()
        for values in self.wave_buffers.values():
            values.clear()
        for key in self.wave_cursors:
            self.wave_cursors[key] = None
        self.update_plots(force=True)

        duration = self.duration_spin.value()
        self.worker = CollectorWorker(
            port=port,
            duration_sec=duration,
            all_trend_defs=self.all_trend_defs,
            all_wave_defs=self.all_wave_defs,
            trend_defs=self.trend_defs,
            wave_defs=self.wave_defs,
            output_name=self.output_name,
        )
        self.worker.package_signal.connect(self.on_package)
        self.worker.status_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.error_signal.connect(self.on_error)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        wave_fs_log = ", ".join(
            [
                f"{item['label']}={item['sample_hz']:.1f}Hz"
                for item in self.wave_defs
            ]
        )
        self.log(
            f"Starting capture on {port}, duration={duration}s, "
            f"config={self.config['path']}, fs: {wave_fs_log}"
        )
        self.worker.start()

    def stop_capture(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.log("Stop requested")

    def on_package(self, payload):
        rel_t = float(payload.get("time", 0.0))

        trend_rows = payload.get("trend_rows", {})
        waves = payload.get("waves", {})
        positive_trend_rows = payload.get("positive_trend_rows", [])
        positive_wave_rows = payload.get("positive_wave_rows", [])

        prev_trend_count = len(self.positive_trend_rows)
        prev_wave_count = len(self.positive_wave_rows)
        self.positive_trend_rows.update(positive_trend_rows)
        self.positive_wave_rows.update(positive_wave_rows)
        if len(self.positive_trend_rows) != prev_trend_count:
            self.selector_filter_dirty["trend"] = True
        if len(self.positive_wave_rows) != prev_wave_count:
            self.selector_filter_dirty["wave"] = True

        if self.simulation_mode:
            self.sim_idle_timer.start()

        # Update wave request catalog: any row that produced positive samples
        # is timestamped, and displayed rows are auto-requested.
        now_mono = time.monotonic()
        displayed_rows = self._displayed_wave_row_ids()
        for row_id in positive_wave_rows:
            self.wave_last_received_at[int(row_id)] = now_mono
        for row_id in displayed_rows:
            self.wave_requested_rows.add(int(row_id))
        self._refresh_wave_request_button_states()

        trend_window, _wave_window = self._effective_windows()
        for row_key, val in trend_rows.items():
            if val is None or math.isnan(val):
                continue
            row_id = int(row_key)
            history = self.trend_history_by_row.get(row_id)
            if history is None:
                history = deque()
                self.trend_history_by_row[row_id] = history
            history.append((rel_t, float(val)))

        cutoff = rel_t - trend_window
        for history in self.trend_history_by_row.values():
            while history and history[0][0] < cutoff:
                history.popleft()

        for idx in range(len(self.trend_defs)):
            self._sync_trend_slot_buffer(idx)

        max_wave_t = rel_t
        for item in self.wave_defs:
            chan_id = item["id"]
            samples = waves.get(chan_id)
            if not samples:
                continue

            sample_period = 1.0 / max(1.0, float(item["sample_hz"]))
            if self.wave_cursors[chan_id] is None:
                self.wave_cursors[chan_id] = rel_t

            for sample in samples:
                t_val = self.wave_cursors[chan_id]
                self.wave_cursors[chan_id] += sample_period
                self.wave_buffers[chan_id].append((t_val, sample))
                max_wave_t = max(max_wave_t, t_val)

        self.logical_now_sec = max(self.logical_now_sec, rel_t, max_wave_t)
        self.update_plots()

    @staticmethod
    def _build_wrapped_series(points, window_sec, now_sec, gap_sec=1.0):
        if not points:
            return [], []

        safe_window = max(0.1, float(window_sec))
        safe_gap = min(max(0.0, float(gap_sec)), max(0.0, safe_window - 0.1))

        x_vals = []
        y_vals = []
        prev_x = None
        for t_val, y_val in points:
            age = now_sec - t_val
            if age < 0.0:
                continue
            if age > (safe_window - safe_gap):
                continue

            x_mod = t_val % safe_window
            if prev_x is not None and x_mod < prev_x:
                x_vals.append(float("nan"))
                y_vals.append(float("nan"))
            x_vals.append(x_mod)
            y_vals.append(y_val)
            prev_x = x_mod
        return x_vals, y_vals

    def update_plots(self, force=False):
        trend_window, wave_window = self._effective_windows()
        now_rel = float(self.logical_now_sec)

        def series_now(points):
            if points:
                return float(points[-1][0])
            return now_rel

        if force:
            for item in self.trend_defs:
                self.trend_curves[item["id"]].setData([], [])
                self.trend_plots[item["id"]].setXRange(
                    0,
                    trend_window,
                    padding=0.0,
                )
            for item in self.wave_defs:
                self.wave_curves[item["id"]].setData([], [])
                self.wave_plots[item["id"]].setXRange(
                    0,
                    wave_window,
                    padding=0.0,
                )
            return

        for item in self.trend_defs:
            points = self.trend_buffers[item["id"]]
            if points:
                this_now = series_now(points)
                x_data, y_data = self._build_wrapped_series(
                    points,
                    trend_window,
                    this_now,
                    gap_sec=1.0,
                )
                self.trend_curves[item["id"]].setData(x_data, y_data)
            self.trend_plots[item["id"]].setXRange(
                0,
                trend_window,
                padding=0.0,
            )

        for item in self.wave_defs:
            points = self.wave_buffers[item["id"]]
            if points:
                this_now = series_now(points)
                x_data, y_data = self._build_wrapped_series(
                    points,
                    wave_window,
                    this_now,
                    gap_sec=1.0,
                )
                self.wave_curves[item["id"]].setData(x_data, y_data)
            self.wave_plots[item["id"]].setXRange(0, wave_window, padding=0.0)

    def on_finished(self, output_file):
        self.update_plots()
        self.log(f"Capture finished. Saved: {output_file}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.simulation_mode:
            self.log("Simulation mode: auto-close in 10s")
            self.sim_idle_timer.start()

    def on_error(self, error_message):
        self.sim_idle_timer.stop()
        self.log(f"ERROR: {error_message}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_simulation_idle_timeout(self):
        self.log("No package for 10 seconds in simulation mode; closing")
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
        QtCore.QTimer.singleShot(800, self.close)

    # --- Waveform request catalog ----------------------------------------

    def _displayed_wave_row_ids(self):
        return {int(item["row_identifier"]) for item in self.wave_defs}

    def _wave_request_button_state(self, row_id):
        requested = row_id in self.wave_requested_rows
        last_rx = self.wave_last_received_at.get(row_id)
        if last_rx is None:
            age = None
        else:
            age = time.monotonic() - last_rx
        receiving = age is not None and age <= self.WAVE_REQUEST_TIMEOUT_SEC

        if requested and receiving:
            return "green"
        if requested and last_rx is None:
            return "blue"
        if requested and not receiving:
            return "red"
        if not requested and receiving:
            return "yellow"
        return "default"

    _WAVE_BTN_STYLES = {
        "green": "background:#3ab36b;color:white;font-weight:600;",
        "blue": "background:#2b83f6;color:white;font-weight:600;",
        "yellow": "background:#f0c419;color:#222;font-weight:600;",
        "red": "background:#d6352b;color:white;font-weight:600;",
        "default": "",
    }

    def _apply_wave_request_button_style(self, row_id):
        if self._is_closing:
            return
        btn = self.wave_request_buttons.get(row_id)
        if btn is None:
            return
        try:
            state = self._wave_request_button_state(row_id)
            btn.setStyleSheet(self._WAVE_BTN_STYLES.get(state, ""))
            btn.setProperty("color_state", state)
            btn.blockSignals(True)
            btn.setChecked(row_id in self.wave_requested_rows)
            btn.blockSignals(False)
        except RuntimeError:
            pass

    def _refresh_wave_request_button_states(self):
        if self._is_closing:
            return
        for row_id in list(self.wave_request_buttons.keys()):
            self._apply_wave_request_button_style(row_id)

    def _on_wave_request_clicked(self, row_id, checked):
        displayed = self._displayed_wave_row_ids()
        if row_id in displayed and not checked:
            # Protect currently displayed rows from being unrequested.
            btn = self.wave_request_buttons.get(row_id)
            if btn is not None:
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)
            self.log(
                f"Wave row #{row_id} is displayed and stays requested"
            )
            return
        if checked:
            self.wave_requested_rows.add(int(row_id))
            self.log(f"Requested wave row #{row_id}")
        else:
            self.wave_requested_rows.discard(int(row_id))
            self.log(f"Cleared request for wave row #{row_id}")
        self._apply_wave_request_button_style(row_id)

    def _save_runtime_config(self):
        cfg_path = Path(self.config.get("path", ""))
        if not cfg_path:
            return

        data = {}
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        data.setdefault("signal_sources", {})
        data.setdefault("ui", {})
        data.setdefault("channels", {})

        data["ui"]["duration_sec"] = int(self.duration_spin.value())
        data["ui"]["trend_window_sec"] = int(self.hr_window_spin.value())
        data["ui"]["wave_window_sec"] = float(self.ecg_window_spin.value())

        data["channels"]["trends"] = [
            {"row_identifier": int(item["row_identifier"])}
            for item in self.trend_defs
        ]
        data["channels"]["waves"] = [
            {"row_identifier": int(item["row_identifier"])}
            for item in self.wave_defs
        ]

        cfg_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )

    def _start_wave_request_state_timer(self):
        if not self.wave_request_state_timer.isActive():
            self.wave_request_state_timer.start()

    def closeEvent(self, event):
        self._is_closing = True
        try:
            self.wave_request_state_timer.stop()
        except Exception:
            pass
        try:
            self.sim_idle_timer.stop()
        except Exception:
            pass
        self._save_runtime_config()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(
        description="Interactive Qt GUI for pycollect capture."
    )
    parser.add_argument(
        "--port",
        default="",
        help="If provided, preselect this port and autostart capture.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Optional duration in seconds.",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Path to JSON config file. Defaults to pycollect_gui_config.json",
    )
    parser.add_argument(
        "--output",
        default="",
        help=(
            "Output filename, for example record.drc. "
            "Default timestamped name is used only when omitted."
        ),
    )
    parser.add_argument(
        "--simulation-mode",
        action="store_true",
        help=(
            "Enable simulator-friendly behavior: collapse sections and "
            "auto-close after 10s of no packages."
        ),
    )
    parser.add_argument(
        "--debug-stdout",
        action="store_true",
        help="Mirror Qt GUI log lines to stdout for debugging.",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    cfg_path = args.config.strip() if args.config else None

    try:
        config = load_signal_config(base_dir, cfg_path)
    except Exception as exc:
        print(f"Failed to load signal config: {exc}", file=sys.stderr)
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)

    if args.duration is not None:
        initial_duration = args.duration
    else:
        initial_duration = config["initial_duration"]

    win = PyCollectQtWindow(
        config=config,
        output_name=args.output.strip(),
        initial_port=args.port.strip() or None,
        autostart=bool(args.port.strip()),
        simulation_mode=args.simulation_mode,
        initial_duration=max(5, int(initial_duration)),
        debug_stdout=args.debug_stdout,
    )
    win.show()
    win.raise_()
    win.activateWindow()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
