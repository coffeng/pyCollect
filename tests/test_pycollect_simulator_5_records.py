#!/usr/bin/env python3
"""Quick test: use copied pycollect.py to read only 5 records from simulator."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

import pycollect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a short pycollect simulator test (5 records)."
    )
    parser.add_argument(
        "--port",
        default="COM1",
        help="Collector input serial port (default: COM1)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.2,
        help="Seconds between reads (default: 0.2)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of records to capture (default: 5)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Reuse pycollect command style so the simulator can start on any command.
    start_waves_command = pycollect.stripspaces(
        "7E58 0000 00E8 FD58 2708 6700 0000 0001 0000 0000 0000 "
        "FF00 0000 0000 0000 0000 0000 0000 0000 0000 0000 0005 "
        "0001 0408 09FF 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0045 7E"
    )
    stop_waves_command = pycollect.stripspaces(
        "7E58 0000 00E8 FD35 2808 6700 0000 0001 0000 0000 0000 "
        "FF00 0000 0000 0000 0000 0000 0000 0000 0000 0001 0005 "
        "0001 FF00 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
        "000F 7E"
    )

    pycollect.send_hex_command(
        args.port,
        bytes.fromhex(start_waves_command),
        "start",
        args.interval,
        args.count,
    )
    pycollect.send_hex_command(
        args.port,
        bytes.fromhex(stop_waves_command),
        "stop",
        0,
        1,
    )


if __name__ == "__main__":
    main()
