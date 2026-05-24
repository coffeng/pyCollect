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
import time
from pathlib import Path

import serial
from serial import SerialException


FLAG = 0x7E
ESC = 0x7D
ESC_XOR = 0x20


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
):
    sent = 0
    base_interval = _estimate_base_interval(records, fallback_interval)
    next_send_time = time.monotonic()
    prev_time = None

    for rec_no, record, rec_time in records:
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

        frame = frame_record(record)
        ser.write(frame)
        sent += 1
        prev_time = rec_time
        if sent % 25 == 0:
            print(f"Sent {sent} records...")
        if max_records > 0 and sent >= max_records:
            break
    print(f"Replay complete: {sent} records sent.")


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

    use_rtscts = False if args.no_rtscts else bool(args.rtscts)
    print(f"Loaded {len(records)} records from {drc_path}")
    print(
        f"Opening {args.port} @ {args.baud}, "
        f"parity={args.parity}, rtscts={use_rtscts}"
    )
    if args.speed is not None:
        print(f"Replay speed: {speed_ctrl.current():.2f}x (CLI override)")
    else:
        print(
            f"Replay speed: {speed_ctrl.current():.2f}x (from {config_path})"
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

            while True:
                replay_once(
                    ser,
                    records,
                    args.max_records,
                    speed_ctrl,
                    args.interval,
                )
                if not args.loop:
                    break
                print("Loop enabled: restarting replay in 1 second...")
                time.sleep(1)
    except SerialException as exc:
        print(f"ERROR: unable to open serial port {args.port}: {exc}")
        print(
            "Hint: another process is likely using this COM port. Stop "
            "the other simulator/collector instance or choose another port."
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
