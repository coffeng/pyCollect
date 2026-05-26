import argparse
import json
import math
import struct
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pyqtgraph as pg
import serial
from PyQt5 import QtCore, QtWidgets
from serial.tools import list_ports

import drc_2_csv
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


def _normalize_signal_key(text):
    if not text:
        return ""
    normalized = []
    for ch in str(text).lower():
        if ch.isalnum():
            normalized.append(ch)
        else:
            normalized.append("_")
    key = "".join(normalized)
    while "__" in key:
        key = key.replace("__", "_")
    return key.strip("_")


def _compact_label_start(text, max_len=8):
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return "Wave"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len]


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

    if len(trend_select) == 0:
        raise SignalConfigError(
            "JSON must declare at least 1 trend row identifier"
        )
    if len(wave_select) == 0:
        raise SignalConfigError(
            "JSON must declare at least 1 waveform row identifier"
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
        selected["id"] = f"t_{row_id}"
        trend_defs.append(selected)

    wave_defs = []
    for idx, item in enumerate(wave_select):
        row_id = int(item["row_identifier"])
        if row_id not in wave_by_row:
            raise SignalConfigError(
                f"Wave row_identifier out of range: {row_id}"
            )
        selected = dict(wave_by_row[row_id])
        selected["id"] = f"w_{row_id}"
        wave_defs.append(selected)

    ui_cfg = raw_cfg.get("ui", {})
    conn_cfg = ui_cfg.get("connection", {})
    initial_duration = int(ui_cfg.get("duration_sec", 60))
    initial_trend_window = float(ui_cfg.get("trend_window_sec", 60))
    initial_wave_window = float(ui_cfg.get("wave_window_sec", 10))
    initial_baudrate = int(conn_cfg.get("baudrate", 19200))
    if initial_baudrate not in (19200, 115200):
        initial_baudrate = 19200
    sim_cfg = ui_cfg.get("simulator", {})
    initial_sim_speed = float(sim_cfg.get("speed_multiplier", 1.0))
    initial_split_ratio = float(ui_cfg.get("graph_split_ratio", 0.5))
    colors = raw_cfg.get("colors", {})
    user_role = raw_cfg.get("user_role", "Administrator")
    if user_role not in ("Administrator", "Reviewer", "Recorded"):
        user_role = "Administrator"

    return {
        "path": str(cfg_path),
        "all_trend_defs": all_trend_defs,
        "all_wave_defs": all_wave_defs,
        "trend_defs": trend_defs,
        "wave_defs": wave_defs,
        "initial_duration": max(5, initial_duration),
        "initial_trend_window": max(10.0, initial_trend_window),
        "initial_wave_window": max(10.0, initial_wave_window),
        "initial_baudrate": initial_baudrate,
        "initial_sim_speed": max(0.05, min(20.0, initial_sim_speed)),
        "initial_split_ratio": max(0.1, min(0.9, initial_split_ratio)),
        "colors": colors,
        "user_role": user_role,
    }


class CollapsibleSection(QtWidgets.QWidget):
    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        self.title = title
        self.toggle_btn = QtWidgets.QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow
        )
        self.toggle_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self.toggle_btn.setStyleSheet("QToolButton { text-align: left; padding-left: 2px; }")

        self.is_locked = False

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
        if self.is_locked and checked:
            # Prevent expanding a locked section.
            self.toggle_btn.blockSignals(True)
            self.toggle_btn.setChecked(False)
            self.toggle_btn.blockSignals(False)
            return
        self.content.setVisible(checked)
        self.toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        self._update_lock_appearance()

    def set_locked(self, locked):
        self.is_locked = locked
        self._update_lock_appearance()

    def _update_lock_appearance(self):
        """Update header appearance based on lock state."""
        base_align = "QToolButton { text-align: left; padding-left: 2px;"
        if self.is_locked:
            self.toggle_btn.setStyleSheet(
                base_align + " color: #888888; background: #1a1a1a; }"
            )
        else:
            self.toggle_btn.setStyleSheet(base_align + " }")
        self._apply_content_lock_state()

    def _apply_content_lock_state(self):
        """Apply lock/unlock styling to all child widgets."""
        for widget in self._get_editable_widgets():
            if self.is_locked:
                # Gray out and disable
                widget.setEnabled(False)
                if isinstance(widget, QtWidgets.QLabel):
                    widget.setStyleSheet("color: #888888;")
                elif isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QSpinBox, QtWidgets.QComboBox)):
                    widget.setStyleSheet("color: #888888; background: #1a1a1a;")
            else:
                # Restore normal appearance
                widget.setEnabled(True)
                if isinstance(widget, QtWidgets.QLabel):
                    widget.setStyleSheet("")
                elif isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QSpinBox, QtWidgets.QComboBox)):
                    widget.setStyleSheet("")
    
    def _get_editable_widgets(self):
        """Get all editable widgets in content area."""
        widgets = []
        for widget in self.content.findChildren(QtWidgets.QWidget):
            if isinstance(widget, (QtWidgets.QLabel, QtWidgets.QLineEdit, QtWidgets.QSpinBox, 
                                 QtWidgets.QComboBox, QtWidgets.QPushButton)):
                widgets.append(widget)
        return widgets

class CollectorWorker(QtCore.QThread):
    package_signal = QtCore.pyqtSignal(object)
    wave_mapping_signal = QtCore.pyqtSignal(object)
    status_signal = QtCore.pyqtSignal(str)
    file_status_signal = QtCore.pyqtSignal(str, str)
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
        baudrate=19200,
        output_name="",
        simulation_mode=False,
        parent=None,
    ):
        super().__init__(parent)
        self.port = port
        self.duration_sec = duration_sec
        self.all_trend_defs = all_trend_defs
        self.all_wave_defs = all_wave_defs
        self.trend_defs = trend_defs
        self.wave_defs = wave_defs
        self.baudrate = (
            int(baudrate)
            if int(baudrate) in (19200, 115200)
            else 19200
        )
        self.output_name = output_name
        self.simulation_mode = bool(simulation_mode)
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
        self.dynamic_wave_types = [
            item["sr_type"]
            for item in wave_defs
            if int(item.get("sr_type", 0)) > 0
        ]
        self._wave_req_lock = threading.Lock()
        # _wave_req_rows will be synced from wave_requested_rows during capture
        self._wave_req_rows = {
            int(item["row_identifier"])
            for item in wave_defs
        }
        self._wave_req_dirty = True

    def _rebuild_wave_type_map(self):
        self.selected_wave_types = {
            sr_type: slot_id
            for sr_type, slot_id in zip(
                self.dynamic_wave_types,
                self.selected_wave_ids,
            )
        }

    def _auto_adapt_wave_mapping(self, sr_types_present):
        if not self.simulation_mode:
            return

        changed = False
        for sr_type in sr_types_present:
            if sr_type <= 0:
                continue
            if sr_type in self.dynamic_wave_types:
                continue
            if len(self.dynamic_wave_types) >= len(self.selected_wave_ids):
                continue
            self.dynamic_wave_types.append(sr_type)
            changed = True

        if changed:
            self._rebuild_wave_type_map()
            self.wave_mapping_signal.emit(list(self.dynamic_wave_types))

    def update_wave_defs(self, new_wave_defs):
        """Thread-safe update of wave definitions from GUI thread."""
        with self._wave_req_lock:
            self.wave_defs = list(new_wave_defs)
            self.selected_wave_ids = [item["id"] for item in self.wave_defs]
            self.dynamic_wave_types = [
                item["sr_type"]
                for item in self.wave_defs
                if int(item.get("sr_type", 0)) > 0
            ]
            self._rebuild_wave_type_map()

    def request_stop(self):
        self._stop_requested = True

    def update_requested_wave_rows(self, row_ids):
        normalized = {
            int(row_id)
            for row_id in (row_ids or [])
            if int(row_id) > 0
        }
        with self._wave_req_lock:
            if normalized == self._wave_req_rows:
                return
            self._wave_req_rows = set(normalized)
            self._wave_req_dirty = True

    def _consume_wave_request_rows(self, force=False):
        with self._wave_req_lock:
            if not force and not self._wave_req_dirty:
                return None
            self._wave_req_dirty = False
            return sorted(self._wave_req_rows)

    @staticmethod
    def _build_wave_request_frame(selected_rows):
        # Template matches the extended WF_REQ packet used by pyCollect.
        template = bytearray(
            bytes.fromhex(pycollect.stripspaces(START_WAVES_HEX))
        )

        req_count_idx = 43
        req_types_start = 45
        checksum_idx = len(template) - 2

        wave_types = [
            int(row_id) & 0xFF
            for row_id in selected_rows
            if int(row_id) > 0
        ]
        wave_types = sorted(set(wave_types))

        max_types = max(0, (checksum_idx - req_types_start) - 1)
        wave_types = wave_types[:max_types]

        template[req_count_idx] = (len(wave_types) + 1) & 0xFF
        for idx in range(req_types_start, checksum_idx):
            template[idx] = 0x00

        write_idx = req_types_start
        for wave_type in wave_types:
            template[write_idx] = int(wave_type) & 0xFF
            write_idx += 1
        template[write_idx] = 0xFF

        checksum = sum(template[1:checksum_idx]) & 0xFF
        template[checksum_idx] = checksum
        return bytes(template)

    def _send(self, ser, hex_command):
        if isinstance(hex_command, (bytes, bytearray)):
            ser.write(bytes(hex_command))
            return
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
        sr_types_present = [payload["sr_types"][idx] for idx in valid_indices]
        self._auto_adapt_wave_mapping(sr_types_present)

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
                "record_time_unix": None,
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
                "record_time_unix": None,
            }

        r_len = header[0]
        r_time = header[4]
        r_maintype = header[8]
        if r_len < 40 or r_len > len(record_data):
            return {
                "trends": {},
                "trend_rows": {},
                "waves": {},
                "positive_trend_rows": [],
                "positive_wave_rows": [],
                "record_time_unix": None,
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
                "record_time_unix": int(r_time),
            }
        if r_maintype == 1:
            waves, positive_wave_rows = self._extract_waves(parsed)
            return {
                "trends": {},
                "trend_rows": {},
                "waves": waves,
                "positive_trend_rows": [],
                "positive_wave_rows": list(positive_wave_rows),
                "record_time_unix": int(r_time),
            }
        return {
            "trends": {},
            "trend_rows": {},
            "waves": {},
            "positive_trend_rows": [],
            "positive_wave_rows": [],
            "record_time_unix": int(r_time),
        }

    def run(self):
        ser = None
        output_file = ""
        output_fp = None
        logical_time_sec = 0.0
        package_counter = 0
        try:
            output_file = pycollect.build_output_filename(self.output_name)
            output_fp = open(output_file, "wb")
            self.file_status_signal.emit("appending", output_file)

            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=5,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                rtscts=True,
            )

            self.status_signal.emit(
                f"Connected to {self.port} @ {self.baudrate}"
            )
            self._send(ser, START_PARAM_HEX)
            initial_rows = self._consume_wave_request_rows(force=True) or []
            self._send(
                ser,
                self._build_wave_request_frame(initial_rows),
            )
            self.status_signal.emit("Capture started")

            while package_counter < self.duration_sec:
                if self._stop_requested:
                    self.status_signal.emit("Stop requested")
                    break

                pending_rows = self._consume_wave_request_rows(force=False)
                if pending_rows is not None:
                    self._send(
                        ser,
                        self._build_wave_request_frame(pending_rows),
                    )
                    self.status_signal.emit(
                        "Wave request updated: "
                        + ",".join(str(v) for v in pending_rows)
                    )

                incoming_data = ser.read_until(bytes([pycollect.FLAG_CHAR]))
                if len(incoming_data) < 40:
                    incoming_data = ser.read_until(
                        bytes([pycollect.FLAG_CHAR])
                    )

                processed = pycollect.process_received_data(incoming_data)
                logical_time_sec += 1.0
                package_counter += 1
                if len(processed) > 40:
                    output_fp.write(processed)
                    output_fp.flush()
                    payload = self._extract_from_record(processed)
                    payload["index"] = package_counter
                    payload["length"] = len(processed)
                    payload["time"] = logical_time_sec
                    self.package_signal.emit(payload)
                    self.status_signal.emit(
                        f"Package {package_counter}/{self.duration_sec}, "
                        f"{len(processed)} bytes"
                    )
                else:
                    self.status_signal.emit(
                        f"Package {package_counter} discarded"
                    )

                # In simulation mode, don't throttle packets to 1 Hz.
                # This allows replay speed multipliers (e.g., 10x) to be
                # reflected in the GUI progression.
                if not self.simulation_mode:
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
            if output_file:
                self.file_status_signal.emit("closed", output_file)
            if ser is not None and ser.is_open:
                ser.close()


class CsvConversionWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(int, int, int)
    finished_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, drc_path, params_path, waves_path, parent=None):
        super().__init__(parent)
        self.drc_path = Path(drc_path)
        self.params_path = Path(params_path)
        self.waves_path = Path(waves_path)

    def _count_records(self):
        total = 0
        with self.drc_path.open("rb") as fp:
            while True:
                header = fp.read(40)
                if len(header) < 40:
                    break
                r_len = struct.unpack_from("<h", header, 0)[0]
                if r_len < 40:
                    break
                total += 1
                skip = r_len - 40
                if skip > 0:
                    fp.seek(skip, 1)
        return max(0, int(total))

    def run(self):
        try:
            total_records = self._count_records()
            self.progress_signal.emit(1, 0, total_records)

            params_df = drc_2_csv.read_params_file(str(self.params_path))
            waves_df = drc_2_csv.read_waves_file(str(self.waves_path))

            def on_progress(processed, _total):
                total = (
                    total_records
                    if total_records > 0
                    else int(_total or 0)
                )
                if total > 0:
                    pct = int(
                        min(
                            90,
                            max(1, (float(processed) * 90.0) / total),
                        )
                    )
                else:
                    pct = 45
                self.progress_signal.emit(pct, int(processed), int(total))

            trend_df, wave_df, freq, pacer_info_list = (
                drc_2_csv.process_drc_file(
                    str(self.drc_path),
                    params_df,
                    waves_df,
                    logger=None,
                    progress_cb=on_progress,
                    total_records=(
                        total_records if total_records > 0 else None
                    ),
                )
            )

            saved_paths = []
            trend_csv_path = str(self.drc_path).replace(".drc", "_trends.csv")
            drc_2_csv.save_dataframe_to_csv(
                trend_df,
                trend_csv_path,
                logger=None,
            )
            saved_paths.append(trend_csv_path)
            self.progress_signal.emit(95, total_records, total_records)

            if freq > 0 and wave_df is not None:
                wave_csv_path = str(self.drc_path).replace(
                    ".drc",
                    "_waves.csv",
                )
                drc_2_csv.save_dataframe_to_csv(
                    wave_df,
                    wave_csv_path,
                    logger=None,
                )
                saved_paths.append(wave_csv_path)
                self.progress_signal.emit(98, total_records, total_records)

            if len(pacer_info_list) > 1:
                drc_2_csv.save_pacers_to_csv(
                    pacer_info_list,
                    str(self.drc_path),
                )
                pacer_csv_path = str(self.drc_path).replace(
                    ".drc",
                    "_pacers.csv",
                )
                saved_paths.append(pacer_csv_path)

            self.progress_signal.emit(100, total_records, total_records)
            self.finished_signal.emit(saved_paths)
        except Exception as exc:
            self.error_signal.emit(str(exc))


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
        self.config_path = Path(config.get("path", ""))
        self.colors = config.get("colors", {})
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
        self.wave_user_unrequested_rows = set()
        self.wave_last_received_at = {}
        self.wave_request_buttons = {}
        self.WAVE_REQUEST_TIMEOUT_SEC = 5.0
        self.capture_started_monotonic = None
        self.first_record_header_utc = None
        self.last_record_header_utc = None
        self.wave_last_seen_monotonic = {}
        self.wave_last_seen_by_row = {}  # Track all waveforms for header
        self.current_output_file = ""
        self.current_file_state = "default"
        self.csv_worker = None
        self.csv_convert_in_progress = False

        self.worker = None
        self.logical_now_sec = 0.0
        self._in_splitter_adjust = False
        self.graph_split_ratio = float(config.get("initial_split_ratio", 0.5))

        self.trend_buffers = {item["id"]: deque() for item in self.trend_defs}
        self.trend_history_by_row = {}
        self.wave_buffers = {item["id"]: deque() for item in self.wave_defs}
        self.wave_cursors = {item["id"]: None for item in self.wave_defs}
        # Pre-populate wave_last_seen_by_row to include all waveforms
        for item in self.all_wave_defs:
            self.wave_last_seen_by_row[int(item["row_identifier"])] = None

        self.trend_plots = {}
        self.trend_curves = {}
        self.wave_plots = {}
        self.wave_curves = {}
        self.trend_catalog_buttons = {}

        self.sim_idle_timer = QtCore.QTimer(self)
        self.sim_idle_timer.setSingleShot(True)
        self.sim_idle_timer.setInterval(10000)
        self.sim_idle_timer.timeout.connect(self._on_simulation_idle_timeout)

        self.wave_request_state_timer = QtCore.QTimer(self)
        self.wave_request_state_timer.setInterval(1000)
        self.wave_request_state_timer.timeout.connect(
            self._refresh_wave_request_button_states
        )
        self.wave_request_state_timer.timeout.connect(
            self._refresh_trend_button_states
        )

        self._apply_pcs_theme()
        self._build_ui()
        self._connect_signals()
        self._restore_lock_state()
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
        # Build initial graph panels from loaded selections.
        self._rebuild_trend_plots()
        self._rebuild_wave_plots()

    def _cfg_color(self, section, key, fallback):
        section_data = self.colors.get(section, {})
        value = section_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    def _resolve_signal_color(self, section, item, fallback):
        palette = self.colors.get(section, {})
        if not isinstance(palette, dict):
            return fallback

        aliases = {
            "hr": "heart_rate",
            "heartrate": "heart_rate",
            "pr": "heart_rate",
            "sys": "systolic",
            "dia": "diastolic",
        }

        candidates = [
            item.get("id", ""),
            item.get("label", ""),
            item.get("title", ""),
        ]
        for raw in candidates:
            key = _normalize_signal_key(raw)
            if not key:
                continue
            for lookup in (key, aliases.get(key, "")):
                if lookup and lookup in palette:
                    value = palette.get(lookup)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        default_color = palette.get("default")
        if isinstance(default_color, str) and default_color.strip():
            return default_color.strip()
        return fallback

    def _style_plot_widget(self, plot):
        plot_bg = self._cfg_color("plot", "background", "#edf1f5")
        grid_color = self._cfg_color("plot", "grid", "#98a4b4")
        border_color = self._cfg_color("plot", "border", "#9aa5b3")
        axis_text_color = self._cfg_color("text", "primary", "#ffffff")
        plot.setBackground(plot_bg)
        plot.showGrid(x=True, y=True, alpha=0.25)
        grid_pen = pg.mkPen(grid_color, width=1)
        plot.getAxis("left").setPen(grid_pen)
        plot.getAxis("bottom").setPen(grid_pen)
        axis_text_pen = pg.mkPen(axis_text_color, width=1)
        plot.getAxis("left").setTextPen(axis_text_pen)
        plot.getAxis("bottom").setTextPen(axis_text_pen)
        plot.getViewBox().setBorder(pg.mkPen(border_color, width=1))

    def _wave_button_style_for_state(self, state):
        status = self.colors.get("status", {})
        buttons = self.colors.get("buttons", {})
        button_states = self.colors.get("button_statuses", {})
        secondary_text = self._cfg_color("text", "secondary", "#222222")
        normal_bg = buttons.get("normal_bg") or "transparent"
        normal_text = buttons.get("normal_text") or secondary_text

        # Prefer explicit per-state button colors from JSON when available.
        state_cfg = button_states.get(state, {})
        default_cfg = button_states.get("default", {})

        def _pick_color(cfg, key):
            value = cfg.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None

        if state == "green":
            bg = (
                _pick_color(state_cfg, "bg")
                or status.get("active")
                or "#3ab36b"
            )
            fg = _pick_color(state_cfg, "text") or "#ffffff"
        elif state == "blue":
            bg = (
                _pick_color(state_cfg, "bg")
                or buttons.get("active_bg")
                or "#2b83f6"
            )
            fg = (
                _pick_color(state_cfg, "text")
                or buttons.get("active_text")
                or "#ffffff"
            )
        elif state == "yellow":
            bg = (
                _pick_color(state_cfg, "bg")
                or status.get("warning")
                or "#f0c419"
            )
            fg = _pick_color(state_cfg, "text") or "#1a1a1a"
        elif state == "red":
            bg = (
                _pick_color(state_cfg, "bg")
                or status.get("alarm")
                or "#d6352b"
            )
            fg = _pick_color(state_cfg, "text") or "#ffffff"
        else:
            bg = (
                _pick_color(state_cfg, "bg")
                or _pick_color(default_cfg, "bg")
                or normal_bg
            )
            fg = (
                _pick_color(state_cfg, "text")
                or _pick_color(default_cfg, "text")
                or normal_text
            )
        return f"background:{bg};color:{fg};font-weight:600;"

    def _apply_pcs_theme(self):
        sidebar_bg = self._cfg_color("sidebar", "background", "#d6dde6")
        sidebar_text = self._cfg_color("sidebar", "text", "#111111")
        sidebar_border = self._cfg_color("sidebar", "border", "#b8c0cb")
        primary_text = self._cfg_color("text", "primary", "#111111")
        secondary_text = self._cfg_color("text", "secondary", "#3e4a5a")
        buttons_normal_bg = self._cfg_color("buttons", "normal_bg", "#c7ced8")
        buttons_normal_text = self._cfg_color(
            "buttons",
            "normal_text",
            primary_text,
        )
        buttons_hover_bg = self._cfg_color("buttons", "hover_bg", "#bec7d2")
        splitter_bg = self._cfg_color("plot", "grid", "#98a4b4")
        inputs_bg = self._cfg_color("plot", "background", "#f1f4f7")

        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background: {sidebar_bg};
                color: {primary_text};
                font-size: 12px;
            }}
            QFrame {{
                background: {sidebar_bg};
                border: 1px solid {sidebar_border};
            }}
            QLabel {{
                color: {primary_text};
            }}
            QToolButton {{
                background: {buttons_normal_bg};
                color: {buttons_normal_text};
                border: 1px solid {sidebar_border};
                border-radius: 3px;
                font-weight: 600;
                padding: 6px;
                text-align: left;
            }}
            QToolButton:hover {{
                background: {buttons_hover_bg};
            }}
            QComboBox, QSpinBox, QDoubleSpinBox, QPushButton {{
                background: {inputs_bg};
                color: {sidebar_text};
                border: 1px solid {sidebar_border};
                border-radius: 3px;
                padding: 4px;
            }}
            QPlainTextEdit {{
                background: {inputs_bg};
                color: {secondary_text};
                border: 1px solid {sidebar_border};
            }}
            QSplitter::handle {{
                background: {splitter_bg};
                width: 6px;
            }}
            """
        )
        pg.setConfigOption(
            "background",
            self._cfg_color("plot", "background", "#edf1f5"),
        )
        pg.setConfigOption("foreground", primary_text)

    def _save_state_colors(self, state):
        button_states = self.colors.get("button_statuses", {})
        buttons = self.colors.get("buttons", {})

        state_cfg = button_states.get(state, {})
        default_cfg = button_states.get("default", {})

        def _pick(cfg, key):
            value = cfg.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None

        bg = (
            _pick(state_cfg, "bg")
            or _pick(default_cfg, "bg")
            or buttons.get("normal_bg")
            or "#1f2d3d"
        )
        fg = (
            _pick(state_cfg, "text")
            or _pick(default_cfg, "text")
            or buttons.get("normal_text")
            or "#ffffff"
        )
        return bg, fg

    def _set_file_save_status(self, state, file_path=""):
        self.current_file_state = state
        self.current_output_file = str(file_path or "").strip()
        text = "No output file"
        if self.current_output_file:
            text = Path(self.current_output_file).name

        bg, fg = self._save_state_colors(state)
        self.save_file_name_label.setText(text)
        self.save_file_name_label.setToolTip(self.current_output_file)
        self.save_file_name_label.setStyleSheet(
            "padding:6px;border-radius:4px;"
            f"background:{bg};color:{fg};font-weight:600;"
        )

        can_convert = (
            state == "green"
            and bool(self.current_output_file)
            and Path(self.current_output_file).exists()
            and not self.csv_convert_in_progress
        )
        self.convert_csv_btn.setVisible(
            state == "green" or self.csv_convert_in_progress
        )
        self.convert_csv_btn.setEnabled(can_convert)
        if not self.csv_convert_in_progress:
            self._set_convert_button_progress(None)

    def _set_convert_button_progress(self, percent):
        if percent is None:
            self.convert_csv_btn.setText("Convert Current DRC to CSV")
            self.convert_csv_btn.setStyleSheet("")
            return

        pct = max(0, min(100, int(percent)))
        split = pct / 100.0
        done_bg = self._cfg_color("buttons", "active_bg", "#00d4ff")
        rest_bg = self._cfg_color("buttons", "normal_bg", "#1a3a52")
        txt = self._cfg_color("buttons", "normal_text", "#e8e8e8")

        self.convert_csv_btn.setText(f"Converting... {pct}%")
        self.convert_csv_btn.setStyleSheet(
            "QPushButton {"
            "font-weight: 600;"
            f"color: {txt};"
            "border-radius: 3px;"
            "padding: 4px;"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {done_bg},"
            f"stop:{split:.4f} {done_bg},"
            f"stop:{split:.4f} {rest_bg},"
            f"stop:1 {rest_bg});"
            "}"
        )

    def _show_saved_csv_paths(self, saved_paths):
        self.convert_saved_list.clear()
        if not saved_paths:
            self.convert_saved_header.setVisible(False)
            self.convert_saved_list.setVisible(False)
            return

        for path_text in saved_paths:
            item = QtWidgets.QListWidgetItem(str(path_text))
            item.setTextAlignment(
                QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
            )
            item.setToolTip(str(path_text))
            self.convert_saved_list.addItem(item)

        self.convert_saved_header.setVisible(True)
        self.convert_saved_list.setVisible(True)

    def _signal_source_paths(self):
        config_path = Path(self.config.get("path", ""))
        base_dir = Path(__file__).resolve().parent
        params_path = base_dir / "params5.txt"
        waves_path = base_dir / "waves5.txt"

        if config_path.exists():
            try:
                raw_cfg = json.loads(config_path.read_text(encoding="utf-8"))
                src = raw_cfg.get("signal_sources", {})
                params_rel = src.get("params_file")
                waves_rel = src.get("waves_file")
                if params_rel:
                    params_path = (base_dir / str(params_rel)).resolve()
                if waves_rel:
                    waves_path = (base_dir / str(waves_rel)).resolve()
            except Exception:
                pass
        return params_path, waves_path

    def convert_current_drc_to_csv(self):
        if self.csv_convert_in_progress:
            return
        if not self.current_output_file:
            self.log("No DRC file available for conversion")
            return

        drc_path = Path(self.current_output_file)
        if not drc_path.exists():
            self.log(f"DRC file not found: {drc_path}")
            return

        params_path, waves_path = self._signal_source_paths()
        if not params_path.exists() or not waves_path.exists():
            self.log(
                "Missing params/waves config files required for CSV conversion"
            )
            return

        self.csv_convert_in_progress = True
        self.convert_csv_btn.setEnabled(False)
        self._set_convert_button_progress(0)
        self._show_saved_csv_paths([])
        self.log(f"Converting to CSV: {drc_path.name}")

        self.csv_worker = CsvConversionWorker(
            drc_path=drc_path,
            params_path=params_path,
            waves_path=waves_path,
            parent=self,
        )
        self.csv_worker.progress_signal.connect(self.on_csv_progress)
        self.csv_worker.finished_signal.connect(self.on_csv_finished)
        self.csv_worker.error_signal.connect(self.on_csv_error)
        self.csv_worker.start()

    def on_csv_progress(self, percent, processed, total):
        self._set_convert_button_progress(percent)
        if total > 0:
            self.convert_csv_btn.setToolTip(f"{processed}/{total} records")
        else:
            self.convert_csv_btn.setToolTip(f"{percent}%")

    def on_csv_finished(self, saved_paths):
        self.csv_convert_in_progress = False
        self._set_file_save_status(
            self.current_file_state,
            self.current_output_file,
        )
        self._show_saved_csv_paths(saved_paths)
        self.log(
            "CSV conversion complete: "
            + ", ".join(Path(p).name for p in saved_paths)
        )
        self.csv_worker = None

    def on_csv_error(self, error_message):
        self.csv_convert_in_progress = False
        self._set_file_save_status(
            self.current_file_state,
            self.current_output_file,
        )
        self._show_saved_csv_paths([])
        self.log(f"CSV conversion failed: {error_message}")
        self.csv_worker = None

    def _on_trend_interval_changed(self, value):
        """Handle trend interval spinner change - save to config."""
        # Save to config
        if self.config_path.exists():
            try:
                cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
                if "ui" not in cfg:
                    cfg["ui"] = {}
                cfg["ui"]["trend_interval_sec"] = value
                self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            except Exception:
                pass

    def _all_lockable_sections(self):
        """All sidebar sections that can be locked (excludes Advanced itself)."""
        return [s for s in [
            getattr(self, "conn_section", None),
            getattr(self, "file_save_section", None),
            getattr(self, "wave_catalog_section", None),
            getattr(self, "view_section", None),
            getattr(self, "capture_section", None),
            getattr(self, "signal_section", None),
            getattr(self, "status_section", None),
        ] if s is not None]

    def _toggle_all_locks(self):
        """Lock all currently-collapsed sections, or unlock all if any are locked."""
        sections = self._all_lockable_sections()
        any_locked = any(s.is_locked for s in sections)
        if any_locked:
            for s in sections:
                s.set_locked(False)
            self._lock_btn.setText("🔓  Lock collapsed sections")
        else:
            for s in sections:
                if not s.toggle_btn.isChecked():  # collapsed
                    s.set_locked(True)
            if any(s.is_locked for s in sections):
                self._lock_btn.setText("🔒  Unlock all sections")
        self._persist_lock_state()

    def _persist_lock_state(self):
        """Persist list of locked section titles to config."""
        if not self.config_path.exists():
            return
        try:
            cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
            cfg.setdefault("ui", {})
            cfg["ui"]["locked_sections"] = [
                s.title for s in self._all_lockable_sections() if s.is_locked
            ]
            self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _restore_lock_state(self):
        """Restore locked sections from config on startup."""
        try:
            if not self.config_path.exists():
                return
            cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
            locked_titles = cfg.get("ui", {}).get("locked_sections", [])
            for s in self._all_lockable_sections():
                if s.title in locked_titles:
                    s.set_locked(True)
            if any(s.is_locked for s in self._all_lockable_sections()):
                self._lock_btn.setText("🔒  Unlock all sections")
        except Exception:
            pass

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.sidebar = QtWidgets.QScrollArea()
        self.sidebar.setMinimumWidth(330)
        self.sidebar.setMaximumWidth(380)
        self.sidebar.setWidgetResizable(True)
        self.sidebar.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.sidebar.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.sidebar.setFrameShape(QtWidgets.QFrame.StyledPanel)

        self.sidebar_content = QtWidgets.QWidget()
        left = QtWidgets.QVBoxLayout(self.sidebar_content)
        left.setContentsMargins(10, 10, 10, 10)
        left.setSpacing(8)

        title = QtWidgets.QLabel("Bedside Monitor Workflow")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 600;"
            f"color:{self._cfg_color('text', 'accent', '#111111')};"
        )
        left.addWidget(title)

        def _hint(text):
            label = QtWidgets.QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(
                "font-size: 11px;"
                f"color:{self._cfg_color('text', 'secondary', '#3e4a5a')};"
            )
            return label

        self.conn_section = CollapsibleSection(
            "Monitor Connection",
            expanded=True,
        )
        left.addWidget(self.conn_section)
        self.port_combo = QtWidgets.QComboBox()
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(["19200", "115200"])
        self.baud_combo.setCurrentText(str(self.config["initial_baudrate"]))
        self.refresh_ports_btn = QtWidgets.QPushButton("Refresh Ports")
        self.conn_section.content_layout.addWidget(
            QtWidgets.QLabel("Source Port")
        )
        conn_row = QtWidgets.QHBoxLayout()
        conn_row.setContentsMargins(0, 0, 0, 0)
        conn_row.setSpacing(6)
        conn_row.addWidget(self.port_combo, 1)
        conn_row.addWidget(QtWidgets.QLabel("Baud"))
        conn_row.addWidget(self.baud_combo)
        conn_row.addWidget(self.refresh_ports_btn)
        self.conn_section.content_layout.addLayout(conn_row)
        
        # Trend interval selector
        trend_interval_row = QtWidgets.QHBoxLayout()
        trend_interval_row.setContentsMargins(0, 0, 0, 0)
        trend_interval_row.setSpacing(6)
        trend_interval_row.addWidget(QtWidgets.QLabel("Trend Interval"))
        self.trend_interval_spin = QtWidgets.QSpinBox()
        self.trend_interval_spin.setMinimum(5)
        self.trend_interval_spin.setMaximum(120)
        self.trend_interval_spin.setSingleStep(5)
        self.trend_interval_spin.setValue(self.config.get("ui", {}).get("trend_interval_sec", 10))
        self.trend_interval_spin.setSuffix(" sec")
        self.trend_interval_spin.valueChanged.connect(self._on_trend_interval_changed)
        trend_interval_row.addWidget(self.trend_interval_spin)
        trend_interval_row.addStretch()
        self.conn_section.content_layout.addLayout(trend_interval_row)
        
        self.conn_section.content_layout.addWidget(
            _hint("Next: confirm monitor source and move to signal setup.")
        )

        self.file_save_section = CollapsibleSection(
            "File Save Status",
            expanded=True,
        )
        left.addWidget(self.file_save_section)
        self.file_save_section.content_layout.addWidget(
            QtWidgets.QLabel("Current DRC File")
        )
        self.save_file_name_label = QtWidgets.QLabel("No output file")
        self.save_file_name_label.setWordWrap(True)
        self.save_file_name_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
        )
        self.file_save_section.content_layout.addWidget(
            self.save_file_name_label
        )

        self.convert_csv_btn = QtWidgets.QPushButton(
            "Convert Current DRC to CSV"
        )
        self.convert_csv_btn.setVisible(False)
        self.convert_csv_btn.setEnabled(False)
        self.convert_csv_btn.clicked.connect(self.convert_current_drc_to_csv)
        self.file_save_section.content_layout.addWidget(self.convert_csv_btn)

        self.convert_saved_header = QtWidgets.QLabel("Saved CSV Files")
        self.convert_saved_header.setVisible(False)
        self.file_save_section.content_layout.addWidget(
            self.convert_saved_header
        )

        self.convert_saved_list = QtWidgets.QListWidget()
        self.convert_saved_list.setVisible(False)
        self.convert_saved_list.setMaximumHeight(88)
        self.convert_saved_list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        self.convert_saved_list.setSelectionMode(
            QtWidgets.QAbstractItemView.NoSelection
        )
        self.convert_saved_list.setFocusPolicy(QtCore.Qt.NoFocus)
        self.convert_saved_list.setTextElideMode(QtCore.Qt.ElideLeft)
        self.file_save_section.content_layout.addWidget(
            self.convert_saved_list
        )

        self.file_save_section.content_layout.addWidget(
            _hint("Blue: appending. Green: closed and ready to convert.")
        )
        self._set_file_save_status("default", "")

        self.view_section = CollapsibleSection(
            "Session Setup",
            expanded=True,
        )
        left.addWidget(self.view_section)

        self.duration_spin = QtWidgets.QSpinBox()
        self.duration_spin.setRange(5, 3600)
        self.duration_spin.setValue(self.config["initial_duration"])
        self.view_section.content_layout.addWidget(
            QtWidgets.QLabel("Record Duration (sec)")
        )
        self.view_section.content_layout.addWidget(self.duration_spin)

        self.hr_window_spin = QtWidgets.QSpinBox()
        self.hr_window_spin.setRange(10, 3600)
        self.hr_window_spin.setValue(int(self.config["initial_trend_window"]))
        self.view_section.content_layout.addWidget(
            QtWidgets.QLabel("Vitals Window (sec)")
        )
        self.view_section.content_layout.addWidget(self.hr_window_spin)

        self.ecg_window_spin = QtWidgets.QDoubleSpinBox()
        self.ecg_window_spin.setRange(10.0, 300.0)
        self.ecg_window_spin.setSingleStep(0.5)
        self.ecg_window_spin.setValue(self.config["initial_wave_window"])
        self.view_section.content_layout.addWidget(
            QtWidgets.QLabel("Waveform Window (sec, 10..300)")
        )
        self.view_section.content_layout.addWidget(self.ecg_window_spin)
        self.view_section.content_layout.addWidget(
            _hint("Next: select waveforms and start monitoring.")
        )

        self.capture_section = CollapsibleSection(
            "Monitoring Control",
            expanded=True,
        )
        left.addWidget(self.capture_section)
        self.start_btn = QtWidgets.QPushButton("Start Monitoring")
        self.stop_btn = QtWidgets.QPushButton("Stop Monitoring")
        self.stop_btn.setEnabled(False)
        self.capture_section.content_layout.addWidget(self.start_btn)
        self.capture_section.content_layout.addWidget(self.stop_btn)
        self.capture_section.content_layout.addWidget(
            _hint("Start to begin bedside recording.")
        )

        self.signal_section = CollapsibleSection("Trends Selection", expanded=True)
        left.addWidget(self.signal_section)
        self.signal_section.content_layout.addWidget(
            _hint(
                "Legend: blue\u00a0=\u00a0has data, green\u00a0=\u00a0selected+data, "
                "light\u00a0green\u00a0=\u00a0selected+no\u00a0data."
            )
        )
        trend_search = QtWidgets.QLineEdit()
        trend_search.setPlaceholderText("Filter trends…")
        trend_search.setClearButtonEnabled(True)
        self.signal_section.content_layout.addWidget(trend_search)

        trend_catalog_scroll = QtWidgets.QScrollArea()
        trend_catalog_scroll.setWidgetResizable(True)
        trend_catalog_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        trend_catalog_scroll.setMinimumHeight(120)
        trend_catalog_scroll.setMaximumHeight(220)
        trend_catalog_inner = QtWidgets.QWidget()
        trend_catalog_grid = QtWidgets.QGridLayout(trend_catalog_inner)
        trend_catalog_grid.setContentsMargins(0, 0, 0, 0)
        trend_catalog_grid.setHorizontalSpacing(4)
        trend_catalog_grid.setVerticalSpacing(4)
        self._trend_catalog_grid = trend_catalog_grid
        self._trend_catalog_items = []

        _trend_cols = 3
        _selected_trend_rows = {int(d["row_identifier"]) for d in self.trend_defs}
        for idx, item in enumerate(self.all_trend_defs):
            row_id = int(item["row_identifier"])
            label = item.get("label") or ""
            btn = QtWidgets.QPushButton(_compact_label_start(label, max_len=8))
            btn.setCheckable(True)
            btn.setChecked(row_id in _selected_trend_rows)
            btn.setToolTip(f"{label} [{item['unit']}]")
            btn.setMinimumWidth(90)
            btn.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Fixed,
            )
            btn.setProperty("row_id", row_id)
            btn.toggled.connect(
                lambda checked, rid=row_id: self._on_trend_catalog_clicked(
                    rid, checked
                )
            )
            self.trend_catalog_buttons[row_id] = btn
            self._trend_catalog_items.append((row_id, label, btn))
            trend_catalog_grid.addWidget(
                btn, idx // _trend_cols, idx % _trend_cols
            )

        trend_catalog_scroll.setWidget(trend_catalog_inner)
        self.signal_section.content_layout.addWidget(trend_catalog_scroll)
        trend_search.textChanged.connect(self._filter_trend_catalog)

        self.status_section = CollapsibleSection("Recorder Output", expanded=True)
        left.addWidget(self.status_section)
        self.status_box = QtWidgets.QPlainTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumBlockCount(500)
        self.status_section.content_layout.addWidget(self.status_box)

        # Waveform Request Catalog: full list of available waveforms.
        # Buttons are color-coded by state machine; see
        # _wave_request_button_state() for transitions. Displayed rows are
        # auto-requested and protected from being unrequested.
        self.wave_catalog_section = CollapsibleSection(
            "Waveform Selection",
            expanded=False,
        )
        left.insertWidget(
            left.indexOf(self.signal_section),
            self.wave_catalog_section,
        )
        self.wave_catalog_section.content_layout.addWidget(
            _hint(
                "Legend: green receiving, yellow delayed, red missing, "
                "blue pending request."
            )
        )
        wave_search = QtWidgets.QLineEdit()
        wave_search.setPlaceholderText("Filter waveforms…")
        wave_search.setClearButtonEnabled(True)
        self.wave_catalog_section.content_layout.addWidget(wave_search)

        catalog_scroll = QtWidgets.QScrollArea()
        catalog_scroll.setWidgetResizable(True)
        catalog_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        catalog_scroll.setMinimumHeight(120)
        catalog_scroll.setMaximumHeight(220)
        catalog_inner = QtWidgets.QWidget()
        catalog_grid = QtWidgets.QGridLayout(catalog_inner)
        catalog_grid.setContentsMargins(0, 0, 0, 0)
        catalog_grid.setHorizontalSpacing(4)
        catalog_grid.setVerticalSpacing(4)
        self._wave_catalog_grid = catalog_grid
        self._wave_catalog_items = []

        cols = 3
        for idx, item in enumerate(self.all_wave_defs):
            row_id = int(item["row_identifier"])
            label = item.get("label") or item.get("title") or ""
            btn = QtWidgets.QPushButton(_compact_label_start(label, max_len=8))
            btn.setCheckable(True)
            btn.setToolTip(label)
            btn.setMinimumWidth(90)
            btn.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Fixed,
            )
            btn.setProperty("row_id", row_id)
            btn.toggled.connect(
                lambda checked, rid=row_id: self._on_wave_request_clicked(
                    rid,
                    checked,
                )
            )
            self.wave_request_buttons[row_id] = btn
            self._wave_catalog_items.append((row_id, label, btn))
            catalog_grid.addWidget(btn, idx // cols, idx % cols)

        catalog_scroll.setWidget(catalog_inner)
        self.wave_catalog_section.content_layout.addWidget(catalog_scroll)
        wave_search.textChanged.connect(self._filter_wave_catalog)

        self.advanced_section = CollapsibleSection("Advanced", expanded=False)
        left.addWidget(self.advanced_section)

        # Single lock button: locks all currently-collapsed sections.
        self._lock_btn = QtWidgets.QPushButton("🔓  Lock collapsed sections")
        self._lock_btn.clicked.connect(self._toggle_all_locks)
        self.advanced_section.content_layout.addWidget(self._lock_btn)
        self.advanced_section.content_layout.addWidget(
            _hint("Locks all currently collapsed sections. Click again to unlock all.")
        )

        self.sim_speed_spin = QtWidgets.QDoubleSpinBox()
        self.sim_speed_spin.setRange(0.05, 20.0)
        self.sim_speed_spin.setSingleStep(0.05)
        self.sim_speed_spin.setValue(self.config["initial_sim_speed"])
        self.advanced_section.content_layout.addWidget(
            QtWidgets.QLabel("Simulator Replay Speed (x)")
        )
        self.advanced_section.content_layout.addWidget(self.sim_speed_spin)
        self.advanced_section.content_layout.addWidget(
            _hint(
                "Updates ui.simulator.speed_multiplier in config on close."
            )
        )

        left.addStretch(1)
        self.sidebar.setWidget(self.sidebar_content)
        layout.addWidget(self.sidebar)

        self.graph_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.graph_splitter.setChildrenCollapsible(False)

        # Trends panel — scrollable; plots are added dynamically by _rebuild_trend_plots
        trends_scroll = QtWidgets.QScrollArea()
        trends_scroll.setWidgetResizable(True)
        trends_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.trends_panel = QtWidgets.QWidget()
        self.trends_layout = QtWidgets.QVBoxLayout(self.trends_panel)
        self.trends_layout.setContentsMargins(0, 0, 0, 0)
        self.trends_layout.setSpacing(4)
        trends_scroll.setWidget(self.trends_panel)

        # Waveforms panel — scrollable; plots are added dynamically by _rebuild_wave_plots
        waves_scroll = QtWidgets.QScrollArea()
        waves_scroll.setWidgetResizable(True)
        waves_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.waves_panel = QtWidgets.QWidget()
        self.waves_layout = QtWidgets.QVBoxLayout(self.waves_panel)
        self.waves_layout.setContentsMargins(0, 0, 0, 0)
        self.waves_layout.setSpacing(4)
        waves_scroll.setWidget(self.waves_panel)

        self.graph_splitter.addWidget(trends_scroll)
        self.graph_splitter.addWidget(waves_scroll)
        self.graph_splitter.setStretchFactor(0, 1)
        self.graph_splitter.setStretchFactor(1, 1)
        self.graph_splitter.setSizes([500, 500])
        self._apply_graph_split_ratio(self.graph_split_ratio)

        # Header above plots: most recent record time and recently active
        # waveforms so clinicians can quickly confirm recency and channels.
        self.graph_header = QtWidgets.QFrame()
        self.graph_header.setFrameShape(QtWidgets.QFrame.StyledPanel)
        header_layout = QtWidgets.QHBoxLayout(self.graph_header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(12)

        self.last_record_label = QtWidgets.QLabel(
            "Last record (header UTC): --"
        )
        self.last_record_label.setStyleSheet(
            "font-weight: 600;"
            f"color:{self._cfg_color('text', 'primary', '#111111')};"
        )
        self.elapsed_label = QtWidgets.QLabel("Elapsed (header): --")
        self.elapsed_label.setStyleSheet(
            "font-weight: 600;"
            f"color:{self._cfg_color('text', 'primary', '#111111')};"
        )
        self.recent_waves_label = QtWidgets.QLabel(
            "Waveforms (last 5s): none"
        )
        self.recent_waves_label.setWordWrap(True)
        self.recent_waves_label.setStyleSheet(
            f"color:{self._cfg_color('text', 'secondary', '#23364d')};"
        )
        header_layout.addWidget(self.last_record_label, 0)
        header_layout.addWidget(self.elapsed_label, 0)
        header_layout.addWidget(self.recent_waves_label, 1)

        self.graph_panel = QtWidgets.QWidget()
        graph_panel_layout = QtWidgets.QVBoxLayout(self.graph_panel)
        graph_panel_layout.setContentsMargins(0, 0, 0, 0)
        graph_panel_layout.setSpacing(8)
        graph_panel_layout.addWidget(self.graph_header)
        graph_panel_layout.addWidget(self.graph_splitter, 1)

        layout.addWidget(self.graph_panel, 1)
        self._update_graph_header()

    def _connect_signals(self):
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        self.start_btn.clicked.connect(self.start_capture)
        self.stop_btn.clicked.connect(self.stop_capture)
        self.hr_window_spin.valueChanged.connect(self.update_plots)
        self.ecg_window_spin.valueChanged.connect(self.update_plots)
        self.graph_splitter.splitterMoved.connect(self.on_splitter_moved)
        self.duration_spin.valueChanged.connect(self._save_runtime_config)

    def _prepare_selector_popups(self):
        pass  # Trend selection is now embedded in the Signal Setup sidebar section.

    def _on_trend_catalog_clicked(self, row_id, checked):
        """Called when a trend catalog button is toggled in the Signal Setup section."""
        row_id = int(row_id)
        selected_row_ids = [int(d["row_identifier"]) for d in self.trend_defs]
        all_trend_by_row = {int(item["row_identifier"]): item for item in self.all_trend_defs}
        if checked and row_id not in selected_row_ids:
            item = all_trend_by_row.get(row_id)
            if item:
                selected = dict(item)
                selected["id"] = f"t_{row_id}"
                self.trend_defs.append(selected)
                if selected["id"] not in self.trend_buffers:
                    self.trend_buffers[selected["id"]] = deque()
                self._sync_all_trend_buffers()
                self._rebuild_trend_plots()
        elif not checked and row_id in selected_row_ids:
            self.trend_defs = [d for d in self.trend_defs
                               if int(d["row_identifier"]) != row_id]
            self._rebuild_trend_plots()
        self._apply_trend_button_style(row_id)

    def _apply_trend_button_style(self, row_id):
        """Color-code a trend catalog button by selection + data state."""
        btn = self.trend_catalog_buttons.get(row_id)
        if btn is None:
            return
        selected = row_id in {int(d["row_identifier"]) for d in self.trend_defs}
        has_positive = row_id in self.positive_trend_rows
        if selected and has_positive:
            bg, fg = "#2fa44f", "#ffffff"       # green
        elif selected and not has_positive:
            bg, fg = "#80c88a", "#1a2a1a"       # light green
        elif not selected and has_positive:
            bg, fg = "#00d4ff", "#0a1428"       # blue
        else:
            bg, fg = "", ""                     # theme default
        try:
            if bg:
                btn.setStyleSheet(f"background-color:{bg}; color:{fg};")
            else:
                btn.setStyleSheet("")
        except RuntimeError:
            pass

    def _refresh_trend_button_states(self):
        """Recolor all trend catalog buttons (called by 1 Hz timer)."""
        if self._is_closing:
            return
        for row_id in list(self.trend_catalog_buttons.keys()):
            self._apply_trend_button_style(row_id)

    def _filter_trend_catalog(self, text):
        """Show only trend buttons whose label contains *text*; reflow grid."""
        query = text.strip().lower()
        grid = self._trend_catalog_grid
        for _, _, btn in self._trend_catalog_items:
            grid.removeWidget(btn)
        col = row_idx = 0
        for _rid, label, btn in self._trend_catalog_items:
            if query and query not in label.lower():
                btn.setVisible(False)
            else:
                btn.setVisible(True)
                grid.addWidget(btn, row_idx, col)
                col += 1
                if col >= 3:
                    col = 0
                    row_idx += 1

    def _filter_wave_catalog(self, text):
        """Show only wave buttons whose label contains *text*; reflow grid."""
        query = text.strip().lower()
        grid = self._wave_catalog_grid
        for _, _, btn in self._wave_catalog_items:
            grid.removeWidget(btn)
        col = row_idx = 0
        for _rid, label, btn in self._wave_catalog_items:
            if query and query not in label.lower():
                btn.setVisible(False)
            else:
                btn.setVisible(True)
                grid.addWidget(btn, row_idx, col)
                col += 1
                if col >= 3:
                    col = 0
                    row_idx += 1

    # --- Graph panel rebuilding ------------------------------------------

    def _calc_graph_min_height(self):
        try:
            screen_h = QtWidgets.QApplication.primaryScreen().size().height()
        except Exception:
            screen_h = 1080
        return max(80, screen_h // 10)

    def _rebuild_trend_plots(self):
        """Clear and recreate trend plots from self.trend_defs."""
        for item_id, plot in list(self.trend_plots.items()):
            self.trends_layout.removeWidget(plot)
            plot.setParent(None)
            plot.deleteLater()
        self.trend_plots.clear()
        self.trend_curves.clear()

        min_h = self._calc_graph_min_height()
        trend_fallbacks = ["#2b83f6", "#24b47e", "#b38ddb", "#6fd3ff"]
        for idx, item in enumerate(self.trend_defs):
            plot = pg.PlotWidget(title=item["title"])
            self._style_plot_widget(plot)
            plot.setLabel("left", text=item["label"], units=item["unit"])
            plot.setMinimumHeight(min_h)
            curve = plot.plot(
                pen=pg.mkPen(
                    self._resolve_signal_color(
                        "trends",
                        item,
                        trend_fallbacks[idx % len(trend_fallbacks)],
                    ),
                    width=2,
                )
            )
            self.trend_plots[item["id"]] = plot
            self.trend_curves[item["id"]] = curve
            self.trends_layout.addWidget(plot)

        self.update_plots()
        self._refresh_trend_button_states()

    def _rebuild_wave_plots(self):
        """Clear and recreate wave plots from self.wave_defs."""
        for item_id, plot in list(self.wave_plots.items()):
            self.waves_layout.removeWidget(plot)
            plot.setParent(None)
            plot.deleteLater()
        self.wave_plots.clear()
        self.wave_curves.clear()

        min_h = self._calc_graph_min_height()
        wave_fallbacks = ["#f23c3c", "#ff8c42", "#ff5a7a", "#f6d743"]
        for idx, item in enumerate(self.wave_defs):
            plot = pg.PlotWidget(title=item["title"])
            self._style_plot_widget(plot)
            plot.setLabel("left", text=item["label"], units=item["unit"])
            plot.setMinimumHeight(min_h)
            curve = plot.plot(
                pen=pg.mkPen(
                    self._resolve_signal_color(
                        "waveforms",
                        item,
                        wave_fallbacks[idx % len(wave_fallbacks)],
                    ),
                    width=1.5,
                )
            )
            self.wave_plots[item["id"]] = plot
            self.wave_curves[item["id"]] = curve
            self.waves_layout.addWidget(plot)

        self.update_plots()

    def _rebuild_wave_defs(self):
        """Rebuild wave_defs (sorted by row_id) from wave_requested_rows."""
        all_wave_by_row = {
            int(item["row_identifier"]): item for item in self.all_wave_defs
        }
        new_wave_defs = []
        for row_id in sorted(self.wave_requested_rows):
            item = all_wave_by_row.get(row_id)
            if item is None:
                continue
            d = dict(item)
            d["id"] = f"w_{row_id}"
            new_wave_defs.append(d)
        # Ensure buffers/cursors exist for all new IDs
        for item in new_wave_defs:
            if item["id"] not in self.wave_buffers:
                self.wave_buffers[item["id"]] = deque()
                self.wave_cursors[item["id"]] = None
        self.wave_defs = new_wave_defs
        if self.worker is not None and self.worker.isRunning():
            self.worker.update_wave_defs(self.wave_defs)

    def _sync_all_trend_buffers(self):
        """Sync all active trend slot buffers from trend_history_by_row."""
        for item in self.trend_defs:
            row_id = item["row_identifier"]
            buf_id = item["id"]
            if buf_id not in self.trend_buffers:
                self.trend_buffers[buf_id] = deque()
            history = self.trend_history_by_row.get(row_id)
            if history is None:
                self.trend_buffers[buf_id].clear()
            else:
                self.trend_buffers[buf_id] = deque(history)

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

    def _apply_graph_split_ratio(self, ratio):
        ratio = min(0.9, max(0.1, float(ratio)))
        total = max(1, sum(self.graph_splitter.sizes()))
        left_px = int(total * ratio)
        right_px = total - left_px
        self._in_splitter_adjust = True
        self.graph_splitter.setSizes([left_px, right_px])
        self._in_splitter_adjust = False

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

        self.graph_split_ratio = clamped_ratio
        self._save_runtime_config()

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
        self.first_record_header_utc = None
        self.last_record_header_utc = None
        self.wave_last_seen_monotonic.clear()
        self.wave_last_seen_by_row.clear()
        self.wave_user_unrequested_rows.clear()
        self.capture_started_monotonic = time.monotonic()
        self.trend_history_by_row.clear()
        for values in self.trend_buffers.values():
            values.clear()
        for values in self.wave_buffers.values():
            values.clear()
        for key in self.wave_cursors:
            self.wave_cursors[key] = None
        self.update_plots(force=True)

        duration = self.duration_spin.value()
        baudrate = int(self.baud_combo.currentText() or "19200")
        self.worker = CollectorWorker(
            port=port,
            duration_sec=duration,
            all_trend_defs=self.all_trend_defs,
            all_wave_defs=self.all_wave_defs,
            trend_defs=self.trend_defs,
            wave_defs=self.wave_defs,
            baudrate=baudrate,
            output_name=self.output_name,
            simulation_mode=self.simulation_mode,
        )
        self.worker.update_requested_wave_rows(self.wave_requested_rows)
        self.worker.package_signal.connect(self.on_package)
        self.worker.wave_mapping_signal.connect(self.on_wave_mapping)
        self.worker.status_signal.connect(self.log)
        self.worker.file_status_signal.connect(self.on_file_status)
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
            f"Starting capture on {port}@{baudrate}, duration={duration}s, "
            f"config={self.config['path']}, fs: {wave_fs_log}"
        )
        self._update_graph_header()
        self.worker.start()

    def on_file_status(self, state, output_file):
        if state == "appending":
            self._set_file_save_status("blue", output_file)
            self.log(f"Appending to: {Path(output_file).name}")
            return
        if state == "closed":
            self._set_file_save_status("green", output_file)
            self.log(f"Closed file: {Path(output_file).name}")

    def stop_capture(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.log("Stop requested")

    def on_wave_mapping(self, wave_row_ids):
        """Wave graphs are driven by catalog buttons; mapping is informational only."""
        pass

    def on_package(self, payload):
        rel_t = float(payload.get("time", 0.0))
        record_time_unix = payload.get("record_time_unix")
        if record_time_unix is not None:
            try:
                record_dt = datetime.fromtimestamp(
                    float(record_time_unix),
                    tz=timezone.utc,
                )
                self.last_record_header_utc = record_dt
                if self.first_record_header_utc is None:
                    self.first_record_header_utc = record_dt
            except Exception:
                pass

        trend_rows = payload.get("trend_rows", {})
        waves = payload.get("waves", {})
        positive_trend_rows = payload.get("positive_trend_rows", [])
        positive_wave_rows = payload.get("positive_wave_rows", [])

        prev_trend_count = len(self.positive_trend_rows)
        prev_wave_count = len(self.positive_wave_rows)
        self.positive_trend_rows.update(positive_trend_rows)
        self.positive_wave_rows.update(positive_wave_rows)
        if len(self.positive_trend_rows) != prev_trend_count:
            self._refresh_trend_button_states()

        if self.simulation_mode:
            # Keep GUI open in simulation mode when stream pauses.
            self.sim_idle_timer.stop()

        # Update wave request catalog: any row that produced positive samples
        # is timestamped, and displayed rows are auto-requested.
        now_mono = time.monotonic()
        displayed_rows = self._displayed_wave_row_ids()
        for row_id in positive_wave_rows:
            row_id = int(row_id)
            self.wave_last_received_at[row_id] = now_mono
            self.wave_last_seen_by_row[row_id] = now_mono
            # Also track waveforms that have actual data (fixes Flow waveform which has zero/negative values)
            for item in self.wave_defs:
                chan_id = item["id"]
                if chan_id in waves and waves[chan_id]:
                    row_id = int(item.get("row_identifier", 0))
                    if row_id > 0:
                        self.wave_last_seen_by_row[row_id] = now_mono
        for row_id in displayed_rows:
            row = int(row_id)
            if row in self.wave_user_unrequested_rows:
                continue
            self.wave_requested_rows.add(row)
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

        self._sync_all_trend_buffers()

        max_wave_t = rel_t
        now_mono = time.monotonic()
        for item in self.wave_defs:
            chan_id = item["id"]
            samples = waves.get(chan_id)
            if not samples:
                continue
            self.wave_last_seen_monotonic[chan_id] = now_mono

            sample_period = 1.0 / max(1.0, float(item["sample_hz"]))
            if self.wave_cursors[chan_id] is None:
                self.wave_cursors[chan_id] = rel_t

            for sample in samples:
                t_val = self.wave_cursors[chan_id]
                self.wave_cursors[chan_id] += sample_period
                self.wave_buffers[chan_id].append((t_val, sample))
                max_wave_t = max(max_wave_t, t_val)

        self.logical_now_sec = max(self.logical_now_sec, rel_t, max_wave_t)
        self._update_graph_header()
        self.update_plots()

    def _update_graph_header(self):
        if self.last_record_header_utc is None:
            self.last_record_label.setText("Last record (header UTC): --")
        else:
            self.last_record_label.setText(
                "Last record (header UTC): "
                f"{self.last_record_header_utc.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        if (
            self.first_record_header_utc is None
            or self.last_record_header_utc is None
        ):
            self.elapsed_label.setText("Elapsed (header): --")
        else:
            elapsed_sec = max(
                0,
                int(
                    (
                        self.last_record_header_utc
                        - self.first_record_header_utc
                    ).total_seconds()
                ),
            )
            hh = elapsed_sec // 3600
            mm = (elapsed_sec % 3600) // 60
            ss = elapsed_sec % 60
            self.elapsed_label.setText(
                f"Elapsed (header): {hh:02d}:{mm:02d}:{ss:02d}"
            )

        now_mono = time.monotonic()
        recent_wave_labels = []
        row_to_label = {
            int(item["row_identifier"]): item["label"]
            for item in self.all_wave_defs
        }
        for row_id in sorted(self.wave_last_seen_by_row.keys()):
            last_seen = self.wave_last_seen_by_row.get(row_id)
            if last_seen is None:
                continue
            if (now_mono - last_seen) <= 5.0:
                label = row_to_label.get(row_id)
                if label:
                    recent_wave_labels.append(label)

        if recent_wave_labels:
            text = ", ".join(recent_wave_labels)
        else:
            text = "none"
        self.recent_waves_label.setText(f"Waveforms (last 5s): {text}")

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
                if item["id"] not in self.trend_curves:
                    continue
                self.trend_curves[item["id"]].setData([], [])
                self.trend_plots[item["id"]].setXRange(
                    0,
                    trend_window,
                    padding=0.0,
                )
            for item in self.wave_defs:
                if item["id"] not in self.wave_curves:
                    continue
                self.wave_curves[item["id"]].setData([], [])
                self.wave_plots[item["id"]].setXRange(
                    0,
                    wave_window,
                    padding=0.0,
                )
            return

        for item in self.trend_defs:
            if item["id"] not in self.trend_curves:
                continue
            points = self.trend_buffers.get(item["id"])
            if points:
                this_now = series_now(points)
                x_data, y_data = self._build_wrapped_series(
                    points,
                    trend_window,
                    this_now,
                    gap_sec=1.0,
                )
                self.trend_curves[item["id"]].setData(x_data, y_data)
                latest = points[-1][1]
                fmt = f"{latest:.0f}" if latest == round(latest) else f"{latest:.1f}"
                self.trend_plots[item["id"]].setTitle(
                    f"{item['title']} : {fmt}"
                )
            self.trend_plots[item["id"]].setXRange(
                0,
                trend_window,
                padding=0.0,
            )

        for item in self.wave_defs:
            if item["id"] not in self.wave_curves:
                continue
            points = self.wave_buffers.get(item["id"])
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
        self.sim_idle_timer.stop()
        self.capture_started_monotonic = None
        self.log(f"Capture finished. Saved: {output_file}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_error(self, error_message):
        self.sim_idle_timer.stop()
        self.capture_started_monotonic = None
        self.log(f"ERROR: {error_message}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_simulation_idle_timeout(self):
        self.log("No package for 10 seconds in simulation mode")

    # --- Waveform request catalog ----------------------------------------

    def _displayed_wave_row_ids(self):
        return {int(item["row_identifier"]) for item in self.wave_defs}

    def _is_actively_appending(self):
        if self.current_file_state != "blue":
            return False
        if self.worker is None:
            return False
        try:
            return self.worker.isRunning()
        except RuntimeError:
            return False

    def _wave_request_button_state(self, row_id):
        requested = row_id in self.wave_requested_rows
        last_rx = self.wave_last_received_at.get(row_id)
        if last_rx is None:
            age = None
        else:
            age = time.monotonic() - last_rx
        receiving = age is not None and age <= self.WAVE_REQUEST_TIMEOUT_SEC
        appending = self._is_actively_appending()
        missing_timeout = False
        if (
            requested
            and last_rx is None
            and appending
            and self.capture_started_monotonic is not None
        ):
            missing_timeout = (
                (time.monotonic() - self.capture_started_monotonic)
                > self.WAVE_REQUEST_TIMEOUT_SEC
            )

        if requested and receiving:
            return "green"
        if requested and last_rx is None and missing_timeout:
            return "red"
        if requested and last_rx is None:
            return "blue"
        if requested and not receiving:
            return "red"
        if not requested and receiving:
            return "yellow"
        return "default"

    def _apply_wave_request_button_style(self, row_id):
        if self._is_closing:
            return
        btn = self.wave_request_buttons.get(row_id)
        if btn is None:
            return
        try:
            state = self._wave_request_button_state(row_id)
            btn.setStyleSheet(self._wave_button_style_for_state(state))
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
        row_id = int(row_id)
        displayed = self._displayed_wave_row_ids()
        appending = self._is_actively_appending()
        if row_id in displayed and not checked and appending:
            state = self._wave_request_button_state(row_id)
            if state != "red":
                # Keep displayed rows selected while actively receiving.
                btn = self.wave_request_buttons.get(row_id)
                if btn is not None:
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                self.log(
                    f"Wave row #{row_id} stays requested while active"
                )
                return
        if checked:
            self.wave_requested_rows.add(row_id)
            self.wave_user_unrequested_rows.discard(row_id)
            self.log(f"Requested wave row #{row_id}")
        else:
            self.wave_requested_rows.discard(row_id)
            self.wave_user_unrequested_rows.add(row_id)
            self.log(f"Cleared request for wave row #{row_id}")

        if self.worker is not None and self.worker.isRunning():
            self.worker.update_requested_wave_rows(self.wave_requested_rows)
        self._rebuild_wave_defs()
        self._rebuild_wave_plots()
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
        data["ui"].setdefault("connection", {})
        data["ui"].setdefault("simulator", {})

        data["ui"]["duration_sec"] = int(self.duration_spin.value())
        data["ui"]["trend_window_sec"] = int(self.hr_window_spin.value())
        data["ui"]["wave_window_sec"] = float(self.ecg_window_spin.value())
        data["ui"]["connection"]["baudrate"] = int(
            self.baud_combo.currentText() or "19200"
        )
        data["ui"]["graph_split_ratio"] = float(self.graph_split_ratio)
        data["ui"]["simulator"]["speed_multiplier"] = float(
            self.sim_speed_spin.value()
        )

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
