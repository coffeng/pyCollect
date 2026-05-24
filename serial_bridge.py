#!/usr/bin/env python3
"""
Simple serial bridge.

Default behavior is one-way forwarding from source to destination, which is
useful for COM2 -> COM1 style test routing.
"""

import argparse
import time

import serial


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Forward bytes from one COM port to another."
    )
    parser.add_argument(
        "--src", default="COM2", help="Source serial port (default: COM2)"
    )
    parser.add_argument(
        "--dst", default="COM1",
        help="Destination serial port (default: COM1)"
    )
    parser.add_argument("--src-baud", type=int, default=115200)
    parser.add_argument("--dst-baud", type=int, default=115200)
    parser.add_argument(
        "--timeout", type=float, default=0.1,
        help="Read timeout in seconds"
    )
    parser.add_argument(
        "--chunk", type=int, default=4096, help="Read chunk size"
    )
    parser.add_argument(
        "--stats-every", type=float, default=5.0,
        help="Print stats every N seconds"
    )
    parser.add_argument(
        "--hex-log", action="store_true",
        help="Print forwarded chunks in hex"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"Opening source {args.src} @ {args.src_baud}")
    print(f"Opening destination {args.dst} @ {args.dst_baud}")

    with serial.Serial(
        args.src, args.src_baud, timeout=args.timeout
    ) as src, serial.Serial(
        args.dst, args.dst_baud, timeout=args.timeout
    ) as dst:
        print("Bridge running. Press Ctrl+C to stop.")
        total = 0
        last_stats = time.time()

        while True:
            data = src.read(args.chunk)
            if data:
                dst.write(data)
                total += len(data)
                if args.hex_log:
                    print(data.hex(" "))

            now = time.time()
            if now - last_stats >= args.stats_every:
                print(f"Forwarded {total} bytes total")
                last_stats = now


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
