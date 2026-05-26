"""
Headless smoke test: send DRC frames on COM4, receive on COM2.
No PyQt. Run with:
    python tests/serial_loopback_test.py
"""
import sys
import threading
import time
from pathlib import Path

# Allow running from repo root or tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import serial
from drc_monitor_simulator import iter_drc_records, frame_record

TX_PORT = "COM4"
RX_PORT = "COM2"
BAUD    = 115200
PARITY  = serial.PARITY_EVEN
RTSCTS  = False          # set True to test with hardware flow control
N_RECORDS = 10           # number of records to send

DRC_PATH = Path(__file__).resolve().parent.parent / "headless_test.drc"


def main():
    if not DRC_PATH.exists():
        print(f"ERROR: DRC file not found: {DRC_PATH}")
        sys.exit(1)

    blob = DRC_PATH.read_bytes()
    records = list(iter_drc_records(blob))
    if not records:
        print("ERROR: No records in DRC file.")
        sys.exit(1)

    to_send = records[:N_RECORDS]
    frames  = [frame_record(r) for _, r, _ in to_send]
    total_bytes = sum(len(f) for f in frames)
    print(f"DRC: {len(records)} records total, will send {len(frames)}")
    print(f"TX={TX_PORT}  RX={RX_PORT}  baud={BAUD}  rtscts={RTSCTS}")

    received_bytes = bytearray()
    rx_error = [None]

    def rx_thread():
        try:
            with serial.Serial(
                port=RX_PORT, baudrate=BAUD, parity=PARITY,
                timeout=3.0, rtscts=RTSCTS
            ) as rx:
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    chunk = rx.read(4096)
                    if chunk:
                        received_bytes.extend(chunk)
                    if len(received_bytes) >= total_bytes:
                        break
        except Exception as e:
            rx_error[0] = e

    t = threading.Thread(target=rx_thread, daemon=True)
    t.start()
    time.sleep(0.3)   # give RX a moment to open

    tx_error = None
    sent_bytes = 0
    try:
        with serial.Serial(
            port=TX_PORT, baudrate=BAUD, parity=PARITY,
            timeout=1.0, write_timeout=2.0, rtscts=RTSCTS
        ) as tx:
            for i, frame in enumerate(frames):
                tx.write(frame)
                sent_bytes += len(frame)
                print(f"  sent record {i+1}/{len(frames)} ({len(frame)} bytes)")
                time.sleep(0.02)
    except Exception as e:
        tx_error = e

    t.join(timeout=5.0)

    print()
    print(f"Sent : {sent_bytes} bytes")
    print(f"Recv : {len(received_bytes)} bytes")

    if tx_error:
        print(f"TX ERROR: {tx_error}")
    if rx_error[0]:
        print(f"RX ERROR: {rx_error[0]}")

    if tx_error or rx_error[0]:
        sys.exit(1)

    if len(received_bytes) < total_bytes:
        print(f"FAIL: received {len(received_bytes)} of {total_bytes} expected bytes")
        sys.exit(1)

    print("PASS: all bytes received")


if __name__ == "__main__":
    main()
