"""Background data collection worker thread for pyCollect GUI."""
import re
import struct
import threading
import time
from datetime import datetime
from pathlib import Path

import serial
from PyQt5 import QtCore

import pycollect

# ---------------------------------------------------------------------------
# S/5 DRI protocol constants
# ---------------------------------------------------------------------------
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

# S/5 Computer Interface Spec (M1017617), alarm request command values
ALARM_CMD_XMIT_STATUS = 0
ALARM_CMD_ENTER_DIFFMODE = 2
ALARM_CMD_EXIT_DIFFMODE = 3
DRI_MT_ALARM = 4
DRI_AL_STATUS = 1


# ---------------------------------------------------------------------------
# CollectorWorker
# ---------------------------------------------------------------------------

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
        trend_interval_sec=None,
        output_name="",
        simulation_mode=False,
        no_rtscts=False,
        alarm_start_hex="",
        alarm_stop_hex="",
        alarm_start_hex_list=None,
        alarm_stop_hex_list=None,
        parent=None,
    ):
        super().__init__(parent)
        self.port = port
        self.duration_sec = duration_sec
        self.all_trend_defs = all_trend_defs
        self.all_wave_defs = all_wave_defs
        self.trend_defs = trend_defs
        self.wave_defs = wave_defs
        self.baudrate = int(baudrate) if int(baudrate) in (19200, 115200) else 19200
        self.trend_interval_sec = trend_interval_sec
        self.output_name = output_name
        self.simulation_mode = bool(simulation_mode)
        self.no_rtscts = bool(no_rtscts)
        self.alarm_start_hex = str(alarm_start_hex or "").strip()
        self.alarm_stop_hex = str(alarm_stop_hex or "").strip()
        self.alarm_start_hex_list = [
            str(item).strip()
            for item in (alarm_start_hex_list or [])
            if str(item).strip()
        ]
        self.alarm_stop_hex_list = [
            str(item).strip()
            for item in (alarm_stop_hex_list or [])
            if str(item).strip()
        ]
        self._stop_requested = False
        self.all_wave_by_type = {item["sr_type"]: item for item in all_wave_defs}
        self.selected_wave_types = {item["sr_type"]: item["id"] for item in wave_defs}
        self.selected_wave_ids = [item["id"] for item in wave_defs]
        self.dynamic_wave_types = [
            item["sr_type"]
            for item in wave_defs
            if int(item.get("sr_type", 0)) > 0
        ]
        self._wave_req_lock = threading.Lock()
        self._wave_req_rows = {int(item["row_identifier"]) for item in wave_defs}
        self._wave_req_dirty = True

        # Last received monitor time (unix timestamp), updated from run() thread.
        self._last_monitor_time_unix = None
        self._last_monitor_time_lock = threading.Lock()

    def _rebuild_wave_type_map(self):
        self.selected_wave_types = {
            sr_type: slot_id
            for sr_type, slot_id in zip(
                self.dynamic_wave_types, self.selected_wave_ids
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
            int(row_id) for row_id in (row_ids or []) if int(row_id) > 0
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

    def last_monitor_time_unix(self):
        """Thread-safe read of the last received monitor record timestamp."""
        with self._last_monitor_time_lock:
            return self._last_monitor_time_unix

    @staticmethod
    def _build_start_param_frame(interval_sec=10):
        """Build a START_PARAM frame with the given trend interval (seconds)."""
        template = bytearray(
            bytes.fromhex(pycollect.stripspaces(START_PARAM_HEX))
        )
        template[42] = int(interval_sec) & 0xFF
        checksum_idx = len(template) - 2
        template[checksum_idx] = sum(template[1:checksum_idx]) & 0xFF
        return bytes(template)

    @staticmethod
    def _build_wave_request_frame(selected_rows):
        template = bytearray(
            bytes.fromhex(pycollect.stripspaces(START_WAVES_HEX))
        )
        req_count_idx = 43
        req_types_start = 45
        checksum_idx = len(template) - 2

        wave_types = sorted(set(
            int(row_id) & 0xFF
            for row_id in selected_rows
            if int(row_id) > 0
        ))
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

    @staticmethod
    def _extract_alarm_strings(payload_bytes):
        chunks = payload_bytes.split(b"\x00")
        found = []
        seen = set()
        for chunk in chunks:
            if len(chunk) < 5:
                continue
            try:
                text = chunk.decode("latin-1", errors="ignore")
            except Exception:
                continue
            text = " ".join(text.split())
            if len(text) < 5 or len(text) > 120:
                continue
            if re.search(r"[A-Za-z]", text) is None:
                continue
            printable = sum(1 for ch in text if 32 <= ord(ch) <= 126)
            if printable < max(4, int(len(text) * 0.8)):
                continue
            key = text.lower()
            if key not in seen:
                seen.add(key)
                found.append(text)
            if len(found) >= 6:
                break
        return found

    @staticmethod
    def _decode_alarm_text_block(raw_bytes):
        text_raw = raw_bytes.split(b"\x00", 1)[0]
        text = text_raw.decode("latin-1", errors="ignore")
        text = " ".join(text.split())
        if len(text) < 3:
            return ""
        if re.search(r"[A-Za-z]", text) is None:
            return ""
        return text

    def _extract_alarm_strings_from_al_disp(self, payload_bytes, raw_offsets, sr_types):
        entries = []
        seen = set()

        valid_indices = [
            idx
            for idx, st in enumerate(sr_types)
            if int(st) > 0 and int(raw_offsets[idx]) >= 0
        ]

        for pos, idx in enumerate(valid_indices):
            sr_type = int(sr_types[idx])
            if sr_type != DRI_AL_STATUS:
                continue

            start = int(raw_offsets[idx])
            if pos < len(valid_indices) - 1:
                end = int(raw_offsets[valid_indices[pos + 1]])
            else:
                end = len(payload_bytes)

            if not (0 <= start < end <= len(payload_bytes)):
                continue

            sub = payload_bytes[start:end]
            layout_candidates = [(10, 100), (10, 96), (8, 96), (12, 96)]
            best_entries = []

            for base, stride in layout_candidates:
                decoded = []
                for block_idx in range(5):
                    entry = base + (block_idx * stride)
                    if entry + 86 > len(sub):
                        break
                    text = self._decode_alarm_text_block(sub[entry:entry + 80])
                    if not text:
                        continue
                    text_changed = int.from_bytes(sub[entry + 80:entry + 82], "little", signed=False)
                    color = int.from_bytes(sub[entry + 82:entry + 84], "little", signed=False)
                    color_changed = int.from_bytes(sub[entry + 84:entry + 86], "little", signed=False)
                    if text_changed not in (0, 1):
                        continue
                    if color_changed not in (0, 1):
                        continue
                    if color < 0 or color > 3:
                        continue
                    decoded.append({"text": text, "color": color})
                if len(decoded) > len(best_entries):
                    best_entries = decoded

            for item in best_entries:
                text = item.get("text", "")
                key = text.lower()
                if key not in seen:
                    seen.add(key)
                    entries.append(item)

        return entries[:5]

    def _extract_trends(self, payload):
        out = {}
        out_invalid = set()
        all_values = {}
        all_invalid_rows = set()
        subgroup_values = {}
        positive_rows = set()

        for offset, sr_type in zip(payload["raw_offsets"], payload["sr_types"]):
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
                int.from_bytes(values_raw[idx:idx + 2], byteorder="little", signed=True)
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
            if raw_value <= pycollect.DATA_INVALID:
                all_values[item["row_identifier"]] = 0.0
                all_invalid_rows.add(item["row_identifier"])
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
            if raw_value <= pycollect.DATA_INVALID:
                out[item["id"]] = 0.0
                out_invalid.add(item["id"])
                continue
            out[item["id"]] = float(raw_value) / item["divider"]

        return out, out_invalid, positive_rows, all_values, all_invalid_rows

    def _extract_waves(self, payload):
        out = {}
        out_invalid = {}
        positive_rows = set()
        present_rows = set()
        valid_indices = [idx for idx, item in enumerate(payload["sr_types"]) if item > 0]
        sr_types_present = [payload["sr_types"][idx] for idx in valid_indices]
        self._auto_adapt_wave_mapping(sr_types_present)

        for pos, idx in enumerate(valid_indices):
            sr_type = payload["sr_types"][idx]
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
                unpack_fmt, wave_bytes[:sample_count * 2]
            )

            wave_meta = self.all_wave_by_type.get(sr_type)
            divider = 1.0
            if wave_meta is not None:
                divider = wave_meta["divider"]

            scaled_samples = []
            invalid_flags = []
            for sample in raw_samples:
                if int(sample) <= pycollect.DATA_INVALID:
                    scaled_samples.append(0.0)
                    invalid_flags.append(True)
                else:
                    scaled_samples.append(float(sample) / divider)
                    invalid_flags.append(False)

            if wave_meta is not None and len(scaled_samples) > 0:
                present_rows.add(wave_meta["row_identifier"])

            if wave_meta is not None and any(abs(s) > 1e-9 for s in scaled_samples):
                positive_rows.add(wave_meta["row_identifier"])

            chan_id = self.selected_wave_types.get(sr_type)
            if not chan_id or chan_id in out:
                continue
            out[chan_id] = scaled_samples
            out_invalid[chan_id] = invalid_flags

        return out, out_invalid, positive_rows, present_rows

    def _extract_from_record(self, record_data):
        _empty = {
            "trends": {},
            "trend_rows": {},
            "waves": {},
            "positive_trend_rows": [],
            "positive_wave_rows": [],
            "record_time_unix": None,
            "record_main_type": None,
        }
        if len(record_data) < 40:
            return _empty

        header_fmt = "< h b b H I b b H h " + "h b" * pycollect.DRI_MAX_SUBRECS
        header_struct = pycollect.struct.Struct(header_fmt)

        try:
            header = header_struct.unpack(record_data[:40])
        except Exception:
            return _empty

        r_len = header[0]
        dri_level = header[2]
        r_time = header[4]
        r_maintype = header[8]
        if r_len < 40 or r_len > len(record_data):
            return _empty

        sr_desc = header[9:]
        raw_offsets = sr_desc[::2]
        raw_types = sr_desc[1::2]
        sr_types = [0 if item < -1 or item > 50 else item for item in raw_types]
        payload = record_data[40:r_len]

        parsed = {"bytes": payload, "raw_offsets": raw_offsets, "sr_types": sr_types}

        alarms = []
        if r_maintype == DRI_MT_ALARM:
            alarms_from_spec = self._extract_alarm_strings_from_al_disp(
                payload, raw_offsets, sr_types
            )
            if alarms_from_spec:
                alarms = alarms_from_spec
            else:
                alarms = [{"text": t, "color": None} for t in self._extract_alarm_strings(payload)]

        if r_maintype == 0:
            trends, trends_invalid, positive_trend_rows, all_trend_rows, invalid_trend_rows = (
                self._extract_trends(parsed)
            )
            return {
                "trends": trends,
                "trends_invalid": list(trends_invalid),
                "trend_rows": all_trend_rows,
                "invalid_trend_rows": list(invalid_trend_rows),
                "waves": {},
                "waves_invalid": {},
                "positive_trend_rows": list(positive_trend_rows),
                "positive_wave_rows": [],
                "present_wave_rows": [],
                "alarms": alarms,
                "record_time_unix": int(r_time),
                "record_main_type": int(r_maintype),
                "dri_level": int(dri_level),
            }
        if r_maintype == 1:
            waves, waves_invalid, positive_wave_rows, present_wave_rows = self._extract_waves(parsed)
            return {
                "trends": {},
                "trends_invalid": [],
                "trend_rows": {},
                "invalid_trend_rows": [],
                "waves": waves,
                "waves_invalid": waves_invalid,
                "positive_trend_rows": [],
                "positive_wave_rows": list(positive_wave_rows),
                "present_wave_rows": list(present_wave_rows),
                "alarms": alarms,
                "record_time_unix": int(r_time),
                "record_main_type": int(r_maintype),
                "dri_level": int(dri_level),
            }
        return {
            "trends": {},
            "trends_invalid": [],
            "trend_rows": {},
            "invalid_trend_rows": [],
            "waves": {},
            "waves_invalid": {},
            "positive_trend_rows": [],
            "positive_wave_rows": [],
            "present_wave_rows": [],
            "alarms": alarms,
            "record_time_unix": int(r_time),
            "record_main_type": int(r_maintype),
            "dri_level": int(dri_level),
        }

    def run(self):
        ser = None
        output_file = ""
        output_fp = None
        pc_start_dt = datetime.now()
        monitor_first_unix = None
        monitor_last_unix = None
        trend_record_count = 0
        waveform_record_count = 0
        alarm_record_count = 0
        logical_time_sec = 0.0
        package_counter = 0
        wave_requests_enabled = False
        try:
            output_file = pycollect.build_output_filename(self.output_name)
            resolved_output = pycollect.resolve_non_overwriting_path(output_file)
            if str(resolved_output) != str(output_file):
                self.status_signal.emit(
                    "Output exists, using timestamped file: "
                    + str(Path(resolved_output).name)
                )
            output_file = str(resolved_output)
            output_fp = open(output_file, "wb")
            self.file_status_signal.emit("appending", output_file)

            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=5,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                rtscts=(not self.no_rtscts),
            )

            self.status_signal.emit(f"Connected to {self.port} @ {self.baudrate}")
            interval = int(self.trend_interval_sec or 10)
            self._send(ser, self._build_start_param_frame(interval))
            alarm_start_frames = list(self.alarm_start_hex_list)
            if not alarm_start_frames and self.alarm_start_hex:
                alarm_start_frames = [self.alarm_start_hex]
            for frame in alarm_start_frames:
                self._send(ser, frame)
            if alarm_start_frames:
                self.status_signal.emit(
                    f"Alarm request sent ({len(alarm_start_frames)} frame(s))"
                )
            initial_rows = self._consume_wave_request_rows(force=True) or []
            if initial_rows:
                self._send(ser, self._build_wave_request_frame(initial_rows))
                wave_requests_enabled = True
            self.status_signal.emit("Capture started")

            while package_counter < self.duration_sec:
                if self._stop_requested:
                    self.status_signal.emit("Stop requested")
                    break

                pending_rows = self._consume_wave_request_rows(force=False)
                if pending_rows is not None:
                    if pending_rows:
                        self._send(ser, self._build_wave_request_frame(pending_rows))
                        wave_requests_enabled = True
                        self.status_signal.emit(
                            "Wave request updated: "
                            + ",".join(str(v) for v in pending_rows)
                        )
                    elif wave_requests_enabled:
                        self._send(ser, STOP_WAVES_HEX)
                        wave_requests_enabled = False
                        self.status_signal.emit("Wave request updated: none")

                incoming_data = ser.read_until(bytes([pycollect.FLAG_CHAR]))
                if len(incoming_data) < 40:
                    incoming_data = ser.read_until(bytes([pycollect.FLAG_CHAR]))

                processed = pycollect.process_received_data(incoming_data)
                package_counter += 1
                if len(processed) > 40:
                    output_fp.write(processed)
                    output_fp.flush()
                    payload = self._extract_from_record(processed)

                    monitor_time = payload.get("record_time_unix")
                    if monitor_time is not None:
                        if monitor_first_unix is None:
                            monitor_first_unix = int(monitor_time)
                        monitor_last_unix = int(monitor_time)
                        with self._last_monitor_time_lock:
                            self._last_monitor_time_unix = int(monitor_time)
                        logical_time_sec = float(
                            int(monitor_time) - monitor_first_unix
                        )
                    else:
                        logical_time_sec += 1.0

                    main_type = payload.get("record_main_type")
                    if main_type == 0:
                        trend_record_count += 1
                    elif main_type == 1:
                        waveform_record_count += 1
                    elif main_type == DRI_MT_ALARM:
                        alarm_record_count += 1

                    payload["index"] = package_counter
                    payload["length"] = len(processed)
                    payload["time"] = logical_time_sec
                    self.package_signal.emit(payload)
                    self.status_signal.emit(
                        f"Package {package_counter}/{self.duration_sec}, "
                        f"{len(processed)} bytes"
                    )
                else:
                    self.status_signal.emit(f"Package {package_counter} discarded")

                if not self.simulation_mode:
                    time.sleep(1)

            self._send(ser, STOP_PARAM_HEX)
            alarm_stop_frames = list(self.alarm_stop_hex_list)
            if not alarm_stop_frames and self.alarm_stop_hex:
                alarm_stop_frames = [self.alarm_stop_hex]
            for frame in alarm_stop_frames:
                self._send(ser, frame)
            if wave_requests_enabled:
                self._send(ser, STOP_WAVES_HEX)
            self.status_signal.emit("Stop commands sent")
            self.finished_signal.emit(output_file)

        except Exception as exc:
            self.error_signal.emit(str(exc))
        finally:
            if output_fp is not None and not output_fp.closed:
                output_fp.close()
            if output_file:
                try:
                    log_file = pycollect.write_drc_capture_log(
                        output_file,
                        pc_start_dt=pc_start_dt,
                        pc_end_dt=datetime.now(),
                        monitor_first_unix=monitor_first_unix,
                        monitor_last_unix=monitor_last_unix,
                        waveforms=[
                            item.get("label") or item.get("id", "")
                            for item in self.wave_defs
                        ],
                        trend_interval_sec=self.trend_interval_sec,
                        trend_record_count=trend_record_count,
                        waveform_record_count=waveform_record_count,
                        alarm_record_count=alarm_record_count,
                    )
                    if log_file:
                        self.status_signal.emit(
                            f"Capture log saved: {Path(log_file).name}"
                        )
                except Exception as exc:
                    self.status_signal.emit(
                        f"WARNING: failed to write capture log: {exc}"
                    )
            if output_file:
                self.file_status_signal.emit("closed", output_file)
            if ser is not None and ser.is_open:
                ser.close()
