#!/usr/bin/env python3
"""
Replay a .drc file as framed serial packets to simulate a GE monitor stream.

Frames are emitted with:
- Start flag: 0x7E
- Escaping: 0x7D + (byte ^ 0x20) for 0x7E/0x7D in payload
- Checksum byte: simple sum(payload) & 0xFF (receiver may ignore)
- End flag: 0x7E

This is designed to be compatible with collectors that unescape data and strip
flag/checksum bytes similarly to the legacy pycollect logic.
"""

import argparse
import json
import struct
import threading
import time
from pathlib import Path

import serial
from local_control import LocalControlServer
from serial import SerialException


FLAG = 0x7E
ESC = 0x7D
ESC_XOR = 0x20
DRI_MAX_SUBRECS = 8
WAVE_MAINTYPE = 1
EOL_SUBR_LIST = 0xFF

HEADER_FMT = "< h b b H I b b H h " + "h b" * DRI_MAX_SUBRECS
HEADER_STRUCT = struct.Struct(HEADER_FMT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay DRC content as monitor-like framed serial packets."
    )
    parser.add_argument(
        "--drc", required=True, help="Path to input .drc file"
    )
    parser.add_argument(
        "--port", default="COM2", help="Output serial port (default: COM2)"
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="Serial baud rate"
    )
    parser.add_argument(
        "--parity",
        choices=["N", "E", "O", "M", "S"],
        default="E",
        help="Serial parity: N,E,O,M,S",
    )
    parser.add_argument(
        "--stopbits", type=float, choices=[1, 1.5, 2], default=1
    )
    parser.add_argument(
        "--bytesize", type=int, choices=[5, 6, 7, 8], default=8
    )
    parser.add_argument(
        "--rtscts", action="store_true", default=True,
        help="Enable RTS/CTS"
    )
    parser.add_argument(
        "--no-rtscts", action="store_true", help="Disable RTS/CTS"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.02,
        help=(
            "Fallback seconds between records when DRC timing cannot be "
            "derived (default: 0.02)"
        ),
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help=(
            "Replay speed multiplier, e.g. 2.0 for 2x. "
            "When omitted, speed is loaded from config and hot-reloaded."
        ),
    )
    parser.add_argument(
        "--config",
        default="pycollect_gui_config.json",
        help=(
            "Path to shared JSON config containing "
            "ui.simulator.speed_multiplier "
            "(default: pycollect_gui_config.json)"
        ),
    )
    parser.add_argument(
        "--loop", action="store_true", help="Loop file replay forever"
    )
    parser.add_argument(
        "--wait-command",
        action="store_true",
        help="Wait until any incoming serial bytes are received before replay",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=0,
        help="Limit records per loop (0 means all)",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=0,
        help="Optional localhost TCP control port (supports: ping,status,stop)",
    )
    parser.add_argument(
        "--simulation-mode",
        action="store_true",
        help="In simulation mode, send all records without waveform filtering; let GUI select waveforms",
    )
    return parser.parse_args()


def _parity(value: str):
    mapping = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    return mapping[value]


def _stopbits(value: float):
    mapping = {
        1: serial.STOPBITS_ONE,
        1.5: serial.STOPBITS_ONE_POINT_FIVE,
        2: serial.STOPBITS_TWO,
    }
    return mapping[value]


def _bytesize(value: int):
    mapping = {
        5: serial.FIVEBITS,
        6: serial.SIXBITS,
        7: serial.SEVENBITS,
        8: serial.EIGHTBITS,
    }
    return mapping[value]


def iter_drc_records(blob: bytes):
    """Yield DRC records by 16-bit little-endian length at offset 0."""
    idx = 0
    rec_no = 0
    total = len(blob)
    while idx + 40 <= total:
        r_len = struct.unpack_from("<h", blob, idx)[0]
        if r_len < 40 or idx + r_len > total:
            break
        rec_no += 1
        record = blob[idx:idx + r_len]
        # DRC record header stores unix time as uint32 at byte offset 6.
        r_time = struct.unpack_from("<I", record, 6)[0]
        yield rec_no, record, float(r_time)
        idx += r_len


def _clamp_speed(value: float) -> float:
    return max(0.05, min(20.0, float(value)))


def _load_speed_from_config(
    config_path: Path,
    default_speed: float,
) -> float:
    if not config_path.exists():
        return default_speed
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return default_speed
    ui_cfg = raw.get("ui", {}) if isinstance(raw, dict) else {}
    sim_cfg = ui_cfg.get("simulator", {}) if isinstance(ui_cfg, dict) else {}
    value = sim_cfg.get("speed_multiplier", default_speed)
    try:
        return _clamp_speed(float(value))
    except Exception:
        return default_speed


def _estimate_base_interval(records, fallback_interval: float) -> float:
    if len(records) < 2:
        return max(0.001, float(fallback_interval))
    first_t = records[0][2]
    last_t = records[-1][2]
    span = max(0.0, last_t - first_t)
    if span <= 0.0:
        return max(0.001, float(fallback_interval))
    return max(0.001, span / max(1, len(records) - 1))


class SpeedController:
    def __init__(self, config_path: Path, speed_override):
        self.config_path = config_path
        self.speed_override = speed_override
        self.current_speed = (
            _clamp_speed(speed_override)
            if speed_override is not None
            else _load_speed_from_config(config_path, 1.0)
        )
        self._last_mtime = None
        if self.config_path.exists():
            try:
                self._last_mtime = self.config_path.stat().st_mtime
            except OSError:
                self._last_mtime = None

    def current(self) -> float:
        return self.current_speed

    def refresh(self) -> bool:
        if self.speed_override is not None:
            return False
        if not self.config_path.exists():
            return False
        try:
            mtime = self.config_path.stat().st_mtime
        except OSError:
            return False
        if self._last_mtime is not None and mtime <= self._last_mtime:
            return False
        self._last_mtime = mtime
        new_speed = _load_speed_from_config(
            self.config_path,
            self.current_speed,
        )
        if abs(new_speed - self.current_speed) < 1e-6:
            return False
        self.current_speed = new_speed
        return True


def escape_payload(payload: bytes) -> bytes:
    out = bytearray()
    for b in payload:
        if b in (FLAG, ESC):
            out.append(ESC)
            out.append(b ^ ESC_XOR)
        else:
            out.append(b)
    return bytes(out)


def frame_record(record: bytes) -> bytes:
    checksum = sum(record) & 0xFF
    payload = record + bytes([checksum])
    framed = bytearray([FLAG])
    framed.extend(escape_payload(payload))
    framed.append(FLAG)
    return bytes(framed)


def _valid_wave_type(value: int) -> bool:
    return 0 < int(value) <= 50


def _decode_frame_body(body: bytes):
    out = bytearray()
    i = 0
    while i < len(body):
        b = body[i]
        if b == ESC and (i + 1) < len(body):
            out.append(body[i + 1] ^ ESC_XOR)
            i += 2
            continue
        out.append(b)
        i += 1
    return bytes(out)


def _iter_frames_from_bytes(buffer: bytearray):
    frames = []
    while True:
        try:
            start = buffer.index(FLAG)
        except ValueError:
            buffer.clear()
            break
        if start > 0:
            del buffer[:start]
        try:
            end = buffer.index(FLAG, 1)
        except ValueError:
            break
        body = bytes(buffer[1:end])
        del buffer[: end + 1]
        decoded = _decode_frame_body(body)
        if len(decoded) < 2:
            continue
        record = decoded[:-1]
        checksum = decoded[-1]
        if (sum(record) & 0xFF) != checksum:
            continue
        frames.append(record)
    return frames


class WaveRequestState:
    def __init__(self):
        self.active = True
        self.selected_types = set()
        self._rx_buffer = bytearray()

    @staticmethod
    def _wave_types_from_request(payload: bytes):
        if len(payload) < 3:
            return []
        # Classic wf_req starts types at +2; extended requests at +4.
        start_idx = 4 if len(payload) > 4 else 2
        if start_idx >= len(payload):
            start_idx = 2

        values = []
        for value in payload[start_idx:]:
            if value == EOL_SUBR_LIST:
                break
            if _valid_wave_type(value):
                values.append(int(value))
        return values

    def _apply_wave_request_record(self, record: bytes):
        if len(record) < 40:
            return
        try:
            header = HEADER_STRUCT.unpack(record[:40])
        except Exception:
            return

        r_len = int(header[0])
        r_maintype = int(header[8])
        if r_maintype != WAVE_MAINTYPE:
            return
        if r_len < 40 or r_len > len(record):
            return

        payload = record[40:r_len]
        if len(payload) < 1:
            return
        req_type = int(payload[0])

        if req_type == 1:  # WF_REQ_CONT_STOP
            self.active = False
            self.selected_types = set()
            return

        wave_types = self._wave_types_from_request(payload)
        self.active = True
        self.selected_types = set(wave_types)

    def process_incoming_bytes(self, data: bytes):
        if not data:
            return
        self._rx_buffer.extend(data)
        for record in _iter_frames_from_bytes(self._rx_buffer):
            self._apply_wave_request_record(record)


def _filter_wave_record(record: bytes, requested_types: set):
    if len(record) < 40:
        return record
    try:
        header = list(HEADER_STRUCT.unpack(record[:40]))
    except Exception:
        return record

    r_len = int(header[0])
    r_maintype = int(header[8])
    if r_maintype != WAVE_MAINTYPE:
        return record
    if r_len < 40 or r_len > len(record):
        return record

    if not requested_types:
        return None

    payload = record[40:r_len]
    sr_desc = header[9:]
    raw_offsets = sr_desc[::2]
    raw_types = sr_desc[1::2]

    valid_indices = []
    for idx, value in enumerate(raw_types):
        wave_type = int(value)
        if _valid_wave_type(wave_type):
            valid_indices.append(idx)

    if not valid_indices:
        return None

    selected_segments = []
    selected_types = []
    payload_len = len(payload)

    for pos, idx in enumerate(valid_indices):
        wave_type = int(raw_types[idx])
        if wave_type not in requested_types:
            continue
        start = int(raw_offsets[idx])
        if pos + 1 < len(valid_indices):
            end = int(raw_offsets[valid_indices[pos + 1]])
        else:
            end = payload_len
        start = max(0, min(start, payload_len))
        end = max(start, min(end, payload_len))
        segment = payload[start:end]
        if not segment:
            continue
        selected_segments.append(segment)
        selected_types.append(wave_type)

    if not selected_segments:
        return None

    new_payload = b"".join(selected_segments)
    new_r_len = 40 + len(new_payload)
    header[0] = int(new_r_len)

    sr_flat = []
    running_offset = 0
    for wave_type, segment in zip(selected_types, selected_segments):
        sr_flat.extend([int(running_offset), int(wave_type)])
        running_offset += len(segment)

    sr_flat.extend([0, -1])
    while len(sr_flat) < 16:
        sr_flat.extend([0, 0])
    sr_flat = sr_flat[:16]

    for idx, value in enumerate(sr_flat):
        header[9 + idx] = int(value)

    try:
        new_header = HEADER_STRUCT.pack(*header)
    except Exception:
        return record
    return new_header + new_payload


def apply_wave_request_filter(record: bytes, wave_state: "WaveRequestState"):
    if wave_state is None:
        return record
    if not wave_state.active:
        try:
            header = HEADER_STRUCT.unpack(record[:40])
            if int(header[8]) == WAVE_MAINTYPE:
                return None
        except Exception:
            return record
        return record
    if not wave_state.selected_types:
        return record
    return _filter_wave_record(record, wave_state.selected_types)


def poll_wave_requests(ser: serial.Serial, wave_state: "WaveRequestState"):
    if wave_state is None:
        return
    while True:
        try:
            data = ser.read(256)
        except Exception:
            return
        if not data:
            break
        wave_state.process_incoming_bytes(data)


def wait_for_any_command(ser: serial.Serial):
    print("Waiting for incoming command bytes before starting replay...")
    buffer = bytearray()
    while True:
        data = ser.read(256)
        if data:
            buffer.extend(data)
            if len(buffer) > 0:
                print(
                    f"Received {len(buffer)} command bytes. "
                    "Starting replay."
                )
                return


def replay_once(
    ser: serial.Serial,
    records,
    max_records: int,
    speed_ctrl: "SpeedController",
    fallback_interval: float,
    wave_state: "WaveRequestState",
    stop_event: threading.Event,
    metrics: dict,
    simulation_mode: bool = False,
):
    sent = 0
    base_interval = _estimate_base_interval(records, fallback_interval)
    next_send_time = time.monotonic()
    prev_time = None

    for rec_no, record, rec_time in records:
        if stop_event.is_set():
            break
        if not simulation_mode:
            poll_wave_requests(ser, wave_state)

        if speed_ctrl.refresh():
            print(
                f"Speed updated from config: {speed_ctrl.current():.2f}x"
            )

        if prev_time is None:
            wait_real = 0.0
        else:
            delta_src = rec_time - prev_time
            if delta_src <= 0:
                delta_src = base_interval
            wait_real = delta_src / speed_ctrl.current()

        next_send_time += wait_real
        delay = next_send_time - time.monotonic()
        if delay > 0:
            time.sleep(delay)

        filtered = record if simulation_mode else apply_wave_request_filter(record, wave_state)
        if filtered is None:
            prev_time = rec_time
            continue

        frame = frame_record(filtered)
        ser.write(frame)
        sent += 1
        metrics["sent_total"] = int(metrics.get("sent_total", 0)) + 1
        prev_time = rec_time
        if sent % 25 == 0:
            print(f"Sent {sent} records...", flush=True)
        if max_records > 0 and sent >= max_records:
            break
    print(f"Replay complete: {sent} records sent.", flush=True)


def main():
    args = parse_args()
    drc_path = Path(args.drc)
    if not drc_path.exists():
        raise FileNotFoundError(f"DRC file not found: {drc_path}")

    blob = drc_path.read_bytes()
    records = list(iter_drc_records(blob))
    if not records:
        raise RuntimeError("No valid DRC records found in input file.")

    config_path = Path(args.config)
    speed_ctrl = SpeedController(config_path, args.speed)
    wave_state = WaveRequestState()
    stop_event = threading.Event()
    metrics = {"sent_total": 0}

    def _on_control_stop():
        stop_event.set()
        return "stopping simulator"

    def _on_control_status():
        return (
            f"running={not stop_event.is_set()} "
            f"sent_total={metrics.get('sent_total', 0)}"
        )

    control = LocalControlServer(
        name="simulator",
        port=args.control_port,
        on_stop=_on_control_stop,
        on_status=_on_control_status,
        logger=lambda msg: print(msg, flush=True),
    )
    control.start()

    use_rtscts = False if args.no_rtscts else bool(args.rtscts)
    print(f"Loaded {len(records)} records from {drc_path}", flush=True)
    print(
        f"Opening {args.port} @ {args.baud}, "
        f"parity={args.parity}, rtscts={use_rtscts}",
        flush=True,
    )
    if args.speed is not None:
        print(f"Replay speed: {speed_ctrl.current():.2f}x (CLI override)", flush=True)
    else:
        print(
            f"Replay speed: {speed_ctrl.current():.2f}x (from {config_path})",
            flush=True,
        )

    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baud,
            timeout=0.2,
            bytesize=_bytesize(args.bytesize),
            parity=_parity(args.parity),
            stopbits=_stopbits(args.stopbits),
            rtscts=use_rtscts,
        ) as ser:
            if args.wait_command:
                wait_for_any_command(ser)
                if not args.simulation_mode:
                    poll_wave_requests(ser, wave_state)

            while True:
                if stop_event.is_set():
                    print("Stop requested by control port", flush=True)
                    break
                replay_once(
                    ser,
                    records,
                    args.max_records,
                    speed_ctrl,
                    args.interval,
                    wave_state,
                    stop_event,
                    metrics,
                    simulation_mode=args.simulation_mode,
                )
                if stop_event.is_set():
                    print("Stop requested by control port", flush=True)
                    break
                if not args.loop:
                    break
                print("Loop enabled: restarting replay in 1 second...", flush=True)
                time.sleep(1)
    except SerialException as exc:
        print(f"ERROR: unable to open serial port {args.port}: {exc}", flush=True)
        print(
            "Hint: another process is likely using this COM port. Stop "
            "the other simulator/collector instance or choose another port.",
            flush=True,
        )
        raise SystemExit(2)
    finally:
        control.stop()


if __name__ == "__main__":
    main()
