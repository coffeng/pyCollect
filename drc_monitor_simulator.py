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
import struct
import time
from pathlib import Path

import serial


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
        help="Seconds between records (default: 0.02)",
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
        yield rec_no, blob[idx:idx + r_len]
        idx += r_len


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
    ser: serial.Serial, records, interval: float, max_records: int
):
    sent = 0
    for rec_no, record in records:
        frame = frame_record(record)
        ser.write(frame)
        sent += 1
        if sent % 25 == 0:
            print(f"Sent {sent} records...")
        if max_records > 0 and sent >= max_records:
            break
        if interval > 0:
            time.sleep(interval)
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

    use_rtscts = False if args.no_rtscts else bool(args.rtscts)
    print(f"Loaded {len(records)} records from {drc_path}")
    print(
        f"Opening {args.port} @ {args.baud}, "
        f"parity={args.parity}, rtscts={use_rtscts}"
    )

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
            replay_once(ser, records, args.interval, args.max_records)
            if not args.loop:
                break
            print("Loop enabled: restarting replay in 1 second...")
            time.sleep(1)


if __name__ == "__main__":
    main()
