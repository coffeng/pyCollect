"""Background COM port scanner for S/5 DRI monitor detection."""
import struct
import time
from datetime import datetime, timedelta

import serial
from PyQt5 import QtCore
from serial.tools import list_ports


class PortScanWorker(QtCore.QThread):
    """Background port scanner thread that emits results via signals."""

    results_signal = QtCore.pyqtSignal(dict)
    finished_signal = QtCore.pyqtSignal()
    error_signal = QtCore.pyqtSignal(str)

    FLAG = 0x7E
    ESCAPE = 0x7D
    ESCAPE_MOD = 0x20
    HEADER_FMT = "< h b b H I b b H h " + "h b" * 8
    HEADER_SIZE = struct.calcsize(HEADER_FMT)
    FAST_PRETEST_TIMEOUT_S = 0.18

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = False

    def run(self):
        try:
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
                self.results_signal.emit({
                    "success_pairs": [],
                    "tooltip_text": "No COM ports found."
                })
                self.finished_signal.emit()
                return

            success_pairs = []
            tooltip_lines = ["Port Scan Results:"]
            tooltip_lines.append(f"Windows UTC offset: {self._format_offset(utc_offset_sec)}")
            tooltip_lines.append("")

            baseline_timeout = 5.0
            baseline_pair = ("COM5", 19200)

            if baseline_pair[0] in ports and not self._stop_requested:
                t0 = time.time()
                rec, mode = self._probe_port(
                    baseline_pair[0],
                    baseline_pair[1],
                    one_shot_timeout_s=4.0,
                    periodic_timeout_s=12.0,
                )
                t1 = time.time()
                if rec is not None:
                    elapsed = t1 - t0
                    baseline_timeout = elapsed + 1.0
                    success_pairs.append(baseline_pair)
                    tooltip_lines.append(
                        f"✓ {baseline_pair[0]} @ {baseline_pair[1]}: {elapsed:.2f}s (baseline)"
                    )

            for port in ports:
                if self._stop_requested:
                    break
                for baud in self.BAUDS:
                    if self._stop_requested:
                        break
                    if (port, baud) == baseline_pair:
                        continue

                    is_candidate, _pre_elapsed = self._pretest_port(port, baud)
                    if not is_candidate:
                        continue

                    one_shot_timeout = min(2.0, baseline_timeout)
                    periodic_timeout = max(0.5, baseline_timeout - one_shot_timeout)
                    pc_before = time.time()
                    rec, mode = self._probe_port(
                        port,
                        baud,
                        one_shot_timeout_s=one_shot_timeout,
                        periodic_timeout_s=periodic_timeout,
                    )
                    pc_after = time.time()
                    elapsed = pc_after - pc_before

                    if rec is not None:
                        success_pairs.append((port, baud))
                        tooltip_lines.append(f"✓ {port} @ {baud}: {elapsed:.2f}s ({mode})")

            if not success_pairs:
                tooltip_lines.append("No S/5 monitors detected.")

            self.results_signal.emit({
                "success_pairs": success_pairs,
                "tooltip_text": "\n".join(tooltip_lines)
            })
        except Exception as e:
            self.error_signal.emit(f"Port scan error: {str(e)}")
        finally:
            self.finished_signal.emit()

    def _unescape(self, data: bytes) -> bytearray:
        out = bytearray()
        it = iter(data)
        for b in it:
            if b == self.ESCAPE:
                nb = next(it, None)
                if nb is not None:
                    out.append(nb ^ self.ESCAPE_MOD)
            else:
                out.append(b)
        if len(out) > self.HEADER_SIZE:
            if out[0] == self.FLAG:
                out = out[1:]
            if out[-1] == self.FLAG:
                out = out[:-1]
            out = out[:-1]
        return out

    def _parse_header(self, record: bytes):
        if len(record) < self.HEADER_SIZE:
            return None
        hdr = struct.unpack(self.HEADER_FMT, record[:self.HEADER_SIZE])
        return {
            "r_len": int(hdr[0]),
            "r_time": int(hdr[4]),
            "r_type": int(hdr[5]),
            "r_maintype": int(hdr[8]),
        }

    def _pretest_port(self, port: str, baud: int, timeout_s: float = None):
        if timeout_s is None:
            timeout_s = self.FAST_PRETEST_TIMEOUT_S
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
            ser.write(self.ONE_SHOT_TREND_REQUEST)
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

    def _probe_port(
        self,
        port: str,
        baud: int,
        one_shot_timeout_s: float,
        periodic_timeout_s: float,
    ):
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
                (self.ONE_SHOT_TREND_REQUEST, "one-shot", one_shot_timeout_s),
                (self.PERIODIC_TREND_REQUEST, "periodic-10s", periodic_timeout_s),
            ):
                ser.reset_input_buffer()
                ser.write(frame)
                t_end = time.monotonic() + float(max(0.2, mode_timeout))

                while time.monotonic() < t_end:
                    incoming_data = ser.read_until(bytes([self.FLAG]))
                    if len(incoming_data) < self.HEADER_SIZE:
                        incoming_data = ser.read_until(bytes([self.FLAG]))

                    record = self._unescape(incoming_data)
                    if len(record) < self.HEADER_SIZE:
                        continue

                    hdr = self._parse_header(bytes(record))
                    if hdr is None:
                        continue
                    if hdr["r_maintype"] != 0:
                        continue

                    try:
                        ser.write(self.STOP_TREND_REQUEST)
                    except Exception:
                        pass
                    return bytes(record), mode_label

                try:
                    ser.write(self.STOP_TREND_REQUEST)
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

    def _format_offset(self, offset_sec: int) -> str:
        sign = "+" if offset_sec >= 0 else "-"
        abs_sec = abs(offset_sec)
        hh = abs_sec // 3600
        mm = (abs_sec % 3600) // 60
        return f"{sign}{hh:02d}:{mm:02d}"

    def request_stop(self):
        self._stop_requested = True
