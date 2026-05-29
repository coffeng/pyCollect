#!/usr/bin/env python3
"""
Standalone S/5 port scanner — no GUI.

Behavior:
- Probe COM ports in descending COM number order (latest USB cable first).
- Probe baud order [19200, 115200] (slow first).
- Measure COM5@19200 response time as baseline when available.
- Use baseline + 1 second as timeout budget for all other combinations.
- Treat monitor timestamp as local time and apply Windows UTC offset in
  clock-difference calculation.
"""

import struct
import sys
import time
from datetime import datetime, timedelta, timezone

import serial
import serial.tools.list_ports as list_ports

FLAG = 0x7E
ESCAPE = 0x7D
ESCAPE_MOD = 0x20

HEADER_FMT = "< h b b H I b b H h " + "h b" * 8
HEADER_SIZE = struct.calcsize(HEADER_FMT)

ONE_SHOT_TREND_REQUEST = bytes.fromhex(
    "7E"
    "3100000000000000000000000000000000000000000000"
    "FF00000000000000000000000000000000000000"
    "01FFFF080000000037"
    "7E"
)

PERIODIC_TREND_REQUEST = bytes.fromhex(
    "7E31 0000 00E8 FD25 0407 6700 0000 0000 0000 0000"
    "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000"
    "0001 0A00 0800 0000 0000 BF7E".replace(" ", "")
)

STOP_TREND_REQUEST = bytes.fromhex(
    "7E31 0000 00E8 FD33 0607 6700 0000 0000 0000 0000"
    "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000"
    "0001 0000 0800 0000 0000 C57E".replace(" ", "")
)

BAUDS = [19200, 115200]
MAINTYPE_NAMES = {0: "PHDB (trend)", 1: "WAVE", 4: "ALARM"}
FAST_PRETEST_TIMEOUT_S = 0.18


def unescape(data: bytes) -> bytearray:
    out = bytearray()
    it = iter(data)
    for b in it:
        if b == ESCAPE:
            nb = next(it, None)
            if nb is not None:
                out.append(nb ^ ESCAPE_MOD)
        else:
            out.append(b)
    if len(out) > HEADER_SIZE:
        if out[0] == FLAG:
            out = out[1:]
        if out[-1] == FLAG:
            out = out[:-1]
        out = out[:-1]
    return out


def parse_header(record: bytes):
    if len(record) < HEADER_SIZE:
        return None
    hdr = struct.unpack(HEADER_FMT, record[:HEADER_SIZE])
    return {
        "r_len": int(hdr[0]),
        "r_time": int(hdr[4]),
        "r_type": int(hdr[5]),
        "r_maintype": int(hdr[8]),
    }


def probe_port(
    port: str,
    baud: int,
    one_shot_timeout_s: float,
    periodic_timeout_s: float,
):
    """Return (record_bytes, mode_label) or (None, None)."""
    ser_timeout = 0.1
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            timeout=ser_timeout,
            write_timeout=0.5,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            rtscts=True,
        )
    except (serial.SerialException, OSError):
        return None, None

    try:
        for frame, mode_label, mode_timeout in (
            (ONE_SHOT_TREND_REQUEST, "one-shot", one_shot_timeout_s),
            (PERIODIC_TREND_REQUEST, "periodic-10s", periodic_timeout_s),
        ):
            ser.reset_input_buffer()
            ser.write(frame)
            t_end = time.monotonic() + float(max(0.2, mode_timeout))

            while time.monotonic() < t_end:
                incoming_data = ser.read_until(bytes([FLAG]))
                if len(incoming_data) < HEADER_SIZE:
                    incoming_data = ser.read_until(bytes([FLAG]))

                record = unescape(incoming_data)
                if len(record) < HEADER_SIZE:
                    continue

                hdr = parse_header(bytes(record))
                if hdr is None:
                    continue
                if hdr["r_maintype"] != 0:
                    continue

                try:
                    ser.write(STOP_TREND_REQUEST)
                except Exception:
                    pass
                return bytes(record), mode_label

            try:
                ser.write(STOP_TREND_REQUEST)
            except Exception:
                pass

        return None, None
    except (serial.SerialException, OSError):
        return None, None
    finally:
        try:
            ser.close()
        except Exception:
            pass


def pretest_port(port: str, baud: int, timeout_s: float = FAST_PRETEST_TIMEOUT_S):
    """Fast activity pretest.

    Returns (is_candidate, elapsed_seconds). A candidate is any port that
    emits at least one byte quickly after a one-shot request.
    """
    t0 = time.time()
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            timeout=0.03,
            write_timeout=0.2,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            rtscts=True,
        )
    except (serial.SerialException, OSError):
        return False, (time.time() - t0)

    try:
        ser.reset_input_buffer()
        ser.write(ONE_SHOT_TREND_REQUEST)

        t_end = time.monotonic() + float(max(0.05, timeout_s))
        while time.monotonic() < t_end:
            chunk = ser.read(min(256, max(1, ser.in_waiting or 1)))
            if chunk:
                return True, (time.time() - t0)
        return False, (time.time() - t0)
    except (serial.SerialException, OSError):
        return False, (time.time() - t0)
    finally:
        try:
            ser.close()
        except Exception:
            pass


def format_offset(offset_sec: int) -> str:
    sign = "+" if offset_sec >= 0 else "-"
    abs_sec = abs(offset_sec)
    hh = abs_sec // 3600
    mm = (abs_sec % 3600) // 60
    return f"{sign}{hh:02d}:{mm:02d} ({offset_sec:+d} sec)"


def main():
    now_local = datetime.now().astimezone()
    utc_offset = now_local.utcoffset() or timedelta(0)
    utc_offset_sec = int(utc_offset.total_seconds())

    seen = set()
    ports = []
    for p in sorted(
        list_ports.comports(),
        key=lambda x: (
            int(x.device[3:])
            if x.device.upper().startswith("COM") and x.device[3:].isdigit()
            else -1,
            x.device,
        ),
        reverse=True,
    ):
        if p.device not in seen:
            seen.add(p.device)
            ports.append(p.device)

    if not ports:
        print("No COM ports found.")
        sys.exit(1)

    print(f"Found {len(ports)} port(s): {', '.join(ports)}")
    print(f"Baud rates: {BAUDS}")
    print(f"Fast pretest timeout: {FAST_PRETEST_TIMEOUT_S*1000:.0f} ms")
    print(f"Windows local UTC offset: {format_offset(utc_offset_sec)}")
    print("Sending one-shot DRI_PH_DISPL request (tx_ival=-1), waiting for one trend record")
    print("=" * 72)

    baseline_pair = ("COM5", 19200)
    baseline_timeout = 5.0
    baseline_result = None

    if baseline_pair[0] in ports:
        t0 = time.time()
        rec, mode = probe_port(
            baseline_pair[0],
            baseline_pair[1],
            one_shot_timeout_s=4.0,
            periodic_timeout_s=12.0,
        )
        t1 = time.time()
        if rec is not None:
            elapsed = t1 - t0
            baseline_timeout = elapsed + 1.0
            baseline_result = (rec, mode, elapsed)
            print(
                f"Baseline response {baseline_pair[0]} @ {baseline_pair[1]}: "
                f"{elapsed:.2f}s"
            )
            print(
                f"Timeout for other combinations: {baseline_timeout:.2f}s "
                "(baseline + 1s)"
            )
        else:
            print(
                f"Baseline {baseline_pair[0]} @ {baseline_pair[1]} not detected; "
                f"using fallback timeout {baseline_timeout:.2f}s"
            )

    found_any = False

    for port in ports:
        for baud in BAUDS:
            label = f"{port} @ {baud}"
            sys.stdout.write(f"  {label:30s} ... ")
            sys.stdout.flush()

            if baseline_result is not None and (port, baud) == baseline_pair:
                record, mode_label, elapsed = baseline_result
                pc_after = time.time()
                pc_before = pc_after - elapsed
            else:
                is_candidate, pre_elapsed = pretest_port(port, baud)
                if not is_candidate:
                    print(f"no response (pretest {pre_elapsed*1000:.0f} ms)")
                    continue

                one_shot_timeout = min(2.0, baseline_timeout)
                periodic_timeout = max(0.5, baseline_timeout - one_shot_timeout)
                pc_before = time.time()
                record, mode_label = probe_port(
                    port,
                    baud,
                    one_shot_timeout_s=one_shot_timeout,
                    periodic_timeout_s=periodic_timeout,
                )
                pc_after = time.time()
                elapsed = pc_after - pc_before

            if record is None:
                print(f"no response ({elapsed:.2f}s)")
                continue

            hdr = parse_header(record)
            if hdr is None or hdr["r_time"] < 946684800:
                print(f"response ({len(record)} bytes) but invalid header")
                continue

            found_any = True
            r_time = hdr["r_time"]
            pc_mid = (pc_before + pc_after) / 2.0

            # Monitor timestamp is local time; convert to UTC-equivalent
            # using current Windows local UTC offset.
            monitor_utc_epoch = float(r_time) - float(utc_offset_sec)
            diff = monitor_utc_epoch - pc_mid

            mon_dt_local = datetime.fromtimestamp(r_time, tz=timezone(utc_offset))
            mon_dt_utc = datetime.fromtimestamp(monitor_utc_epoch, tz=timezone.utc)
            pc_dt_local = datetime.fromtimestamp(pc_mid, tz=timezone(utc_offset))
            pc_dt_utc = datetime.fromtimestamp(pc_mid, tz=timezone.utc)
            mt_name = MAINTYPE_NAMES.get(hdr["r_maintype"], str(hdr["r_maintype"]))

            print("S/5 FOUND")
            print(f"    Monitor time : {mon_dt_local.strftime('%Y-%m-%d %H:%M:%S %z')}  (raw {r_time})")
            print(f"    Monitor UTC  : {mon_dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"    PC local     : {pc_dt_local.strftime('%Y-%m-%d %H:%M:%S %z')}  (unix {int(pc_mid)})")
            print(f"    PC UTC       : {pc_dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"    Offset used  : {format_offset(utc_offset_sec)}")
            print(f"    Clock diff   : {diff:+.1f} s  (monitor minus PC, offset-adjusted)")
            print(f"    Record       : len={hdr['r_len']}, type={mt_name}, raw={len(record)} bytes")
            print(f"    Probe mode   : {mode_label}")
            print(f"    Probe time   : {elapsed:.2f} s")
            break

    print("=" * 72)
    if found_any:
        print("Done — at least one S/5 monitor detected.")
    else:
        print("Done — no S/5 monitors detected on any port.")


if __name__ == "__main__":
    main()
