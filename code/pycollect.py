import argparse
import collections
import json
import os
import subprocess
import struct
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import serial  # pyserial is assumed to be available


FLAG_CHAR = 0x7E
ESCAPE_CHAR = 0x7D
ESCAPE_MOD = 0x20
DATA_INVALID = -32760
DRI_MAX_SUBRECS = 8


def _runtime_roots():
    roots = []

    if getattr(sys, "frozen", False):
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            local_root = Path(local_appdata) / "pyCollect"
            roots.append(local_root)
            roots.append(local_root / "config")

        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir)
        roots.append(exe_dir / "config")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass).resolve())
            roots.append((Path(meipass).resolve() / "config"))
        roots.append(Path.cwd().resolve())
    else:
        roots.append(Path.cwd().resolve())
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            local_root = Path(local_appdata) / "pyCollect"
            roots.append(local_root)
            roots.append(local_root / "config")
        repo_root = Path(__file__).resolve().parent.parent
        roots.append(repo_root)
        roots.append(repo_root / "config")

    unique = []
    seen = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def resolve_gui_config_path(config_path=None):
    """Resolve GUI JSON config path across script/exe runtime locations."""
    default_name = "pycollect_gui_config.json"

    if config_path:
        requested = Path(config_path)
        if requested.is_absolute() and requested.exists():
            return requested
        if requested.exists():
            return requested.resolve()

        for root in _runtime_roots():
            candidate = (root / config_path).resolve()
            if candidate.exists():
                return candidate
            if requested.name == default_name:
                fallback = (root / default_name).resolve()
                if fallback.exists():
                    return fallback
        return None

    for root in _runtime_roots():
        candidate = (root / default_name).resolve()
        if candidate.exists():
            return candidate
    return None


def _startup_log_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    out_dir = base_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "pycollect_startup.log"


def _startup_log(message):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _startup_log_path().open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


class LiveMonitorPlot:
    """Simple live plot for first detected heart rate and ECG waveform."""

    def __init__(
        self,
        hr_window_points=10,
        ecg_window_samples=5000,
        refresh_interval_sec=10,
        keep_foreground=True,
    ):
        try:
            import matplotlib.pyplot as plt
        except Exception as exc:
            raise RuntimeError(
                "GUI mode requires matplotlib. "
                "Install it with: pip install matplotlib"
            ) from exc

        self.plt = plt
        self.hr_points = collections.deque(maxlen=hr_window_points)
        self.ecg_points = collections.deque(maxlen=ecg_window_samples)
        self.refresh_interval_sec = max(1, int(refresh_interval_sec))
        self.keep_foreground = keep_foreground
        self.last_draw_time = 0.0

        self.plt.ion()
        self.fig, (self.ax_hr, self.ax_ecg) = self.plt.subplots(
            2,
            1,
            figsize=(10, 6),
        )
        self.fig.suptitle("pycollect Live View")

        self.hr_line, = self.ax_hr.plot([], [], "b-")
        self.ax_hr.set_title("Heart Rate (first detected trend value)")
        self.ax_hr.set_ylabel("bpm")
        self.ax_hr.grid(True, alpha=0.3)
        self.ax_hr.set_xlim(0, max(10, hr_window_points))
        self.ax_hr.set_ylim(40, 140)

        self.ecg_line, = self.ax_ecg.plot([], [], "r-")
        self.ax_ecg.set_title("ECG Waveform (first detected wave channel)")
        self.ax_ecg.set_ylabel("raw")
        self.ax_ecg.set_xlabel("sample")
        self.ax_ecg.grid(True, alpha=0.3)
        self.ax_ecg.set_xlim(0, max(200, ecg_window_samples))
        self.ax_ecg.set_ylim(-100, 100)

        self.status_text = self.fig.text(
            0.5,
            0.01,
            "Waiting for HR/ECG data...",
            ha="center",
            va="bottom",
        )

        self.fig.tight_layout()
        self.fig.canvas.draw()
        self._show_and_raise_window()
        self._draw(force=True)

    def _show_and_raise_window(self):
        self.plt.show(block=False)
        manager = self.fig.canvas.manager
        window = getattr(manager, "window", None)

        if window is None:
            return

        if not self.keep_foreground:
            return

        # Try Qt window controls first; fallback to Tk if available.
        try:
            if hasattr(window, "showNormal"):
                window.showNormal()
            if hasattr(window, "raise_"):
                window.raise_()
            if hasattr(window, "activateWindow"):
                window.activateWindow()
        except Exception:
            pass

        try:
            if hasattr(window, "attributes"):
                window.attributes("-topmost", 1)
                window.attributes("-topmost", 0)
            if hasattr(window, "wm_attributes"):
                window.wm_attributes("-topmost", 1)
                window.wm_attributes("-topmost", 0)
        except Exception:
            pass

    def _draw(self, force=False):
        now = time.time()
        if (
            not force
            and (now - self.last_draw_time) < self.refresh_interval_sec
        ):
            return
        self.last_draw_time = now

        hr_count = len(self.hr_points)
        ecg_count = len(self.ecg_points)
        self.status_text.set_text(
            f"Last {hr_count} HR points, {ecg_count} ECG samples | "
            f"refresh every {self.refresh_interval_sec}s"
        )

        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        self.plt.pause(0.001)

    def update(self, hr_value=None, ecg_samples=None):
        if hr_value is not None:
            self.hr_points.append(hr_value)

        if ecg_samples:
            self.ecg_points.extend(ecg_samples)

        if self.hr_points:
            y_hr = list(self.hr_points)
            x_hr = list(range(len(y_hr)))
            self.hr_line.set_data(x_hr, y_hr)
            self.ax_hr.set_xlim(0, max(10, len(y_hr)))
            hr_min = min(y_hr)
            hr_max = max(y_hr)
            if hr_min == hr_max:
                hr_min -= 1
                hr_max += 1
            self.ax_hr.set_ylim(hr_min - 2, hr_max + 2)

        if self.ecg_points:
            y_ecg = list(self.ecg_points)
            x_ecg = list(range(len(y_ecg)))
            self.ecg_line.set_data(x_ecg, y_ecg)
            self.ax_ecg.set_xlim(0, max(200, len(y_ecg)))
            ecg_min = min(y_ecg)
            ecg_max = max(y_ecg)
            if ecg_min == ecg_max:
                ecg_min -= 1
                ecg_max += 1
            margin = max(2, int((ecg_max - ecg_min) * 0.1))
            self.ax_ecg.set_ylim(ecg_min - margin, ecg_max + margin)

        self._draw(force=False)

    def close(self):
        self.plt.ioff()
        self.plt.close(self.fig)


def extract_first_hr_and_ecg(record_data):
    """Extract first HR-like trend value and first ECG-like wave samples."""
    if len(record_data) < 40:
        return None, None

    header_fmt = "< h b b H I b b H h " + "h b" * DRI_MAX_SUBRECS
    header_struct = struct.Struct(header_fmt)

    try:
        header = header_struct.unpack(record_data[:40])
    except struct.error:
        return None, None

    r_len = header[0]
    r_maintype = header[8]
    if r_len < 40 or r_len > len(record_data):
        return None, None

    sr_desc = header[9:]
    raw_offsets = sr_desc[::2]
    raw_types = sr_desc[1::2]
    sr_types = [0 if t < -1 or t > 50 else t for t in raw_types]
    payload = record_data[40:r_len]

    first_hr = None
    first_ecg = None

    if r_maintype == 0:
        for offset, sr_type in zip(raw_offsets, sr_types):
            if sr_type <= 0:
                continue

            start = offset
            end = start + 279
            if start < 0 or end > len(payload):
                continue

            trend_subrecord = payload[start:end]
            values_bytes = trend_subrecord[4:274]
            if len(values_bytes) < 2:
                continue

            values = [
                int.from_bytes(
                    values_bytes[i:i + 2],
                    byteorder="little",
                    signed=True,
                )
                for i in range(0, len(values_bytes), 2)
            ]
            for value in values:
                if value == DATA_INVALID:
                    continue
                if 20 <= value <= 250:
                    first_hr = value
                    break
            if first_hr is not None:
                break

    elif r_maintype == 1:
        valid_indices = [
            index for index, item in enumerate(sr_types) if item > 0
        ]
        if valid_indices:
            index = valid_indices[0]
            start = raw_offsets[index] + 6
            if index < len(valid_indices) - 1:
                next_index = valid_indices[index + 1]
                end = raw_offsets[next_index]
            else:
                end = len(payload)

            if 0 <= start < end <= len(payload):
                wave_bytes = payload[start:end]
                if len(wave_bytes) >= 2:
                    sample_count = len(wave_bytes) // 2
                    unpack_fmt = "<" + "h" * sample_count
                    first_ecg = list(
                        struct.unpack(
                            unpack_fmt,
                            wave_bytes[:sample_count * 2],
                        )
                    )

    return first_hr, first_ecg


def process_received_data(data):
    """Unescape bytes and strip frame flags/checksum from received data."""
    processed_data = bytearray()

    iterator = iter(data)
    for byte in iterator:
        if byte == ESCAPE_CHAR:
            next_byte = next(iterator, None)
            if next_byte is not None:
                processed_data.append(next_byte ^ ESCAPE_MOD)
        else:
            processed_data.append(byte)

    if len(processed_data) > 40:
        if processed_data[0] == FLAG_CHAR:
            processed_data = processed_data[1:]
        if processed_data[-1] == FLAG_CHAR:
            processed_data = processed_data[:-1]
        processed_data = processed_data[:-1]

    return processed_data


def build_output_filename(output_name=None):
    """Build output filename using default timestamp only when name omitted."""
    timestamp = datetime.now().strftime("%y%m%d%H%M%S")
    if not output_name:
        return f"record_{timestamp}.drc"

    cleaned = output_name.strip()
    if not cleaned:
        return f"record_{timestamp}.drc"

    root, ext = os.path.splitext(cleaned)
    if not ext:
        return f"{cleaned}.drc"

    return cleaned


def send_hex_command(
    port,
    command_bytes,
    operation_type,
    interval,
    count,
    plotter=None,
    output_name=None,
    baudrate=115200,
    use_rtscts=True,
):
    """Send command and optionally capture/process response packages."""
    ser = None
    try:
        ser = serial.Serial(
            port=port,
            baudrate=int(baudrate),
            timeout=5,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            rtscts=bool(use_rtscts),
        )

        concatenated_data = bytearray()
        if interval == 0:
            interval = 10

        ser.write(command_bytes)

        if operation_type == "start":
            for index in range(count):
                incoming_data = ser.read_until(bytes([FLAG_CHAR]))

                if len(incoming_data) < 40:
                    incoming_data = ser.read_until(bytes([FLAG_CHAR]))

                processed_data = process_received_data(incoming_data)

                if len(processed_data) > 40:
                    concatenated_data.extend(processed_data)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(
                        f"Package {index + 1} received at {now}, "
                        f"length: {len(processed_data)} bytes"
                    )

                    if plotter is not None:
                        hr_value, ecg_samples = extract_first_hr_and_ecg(
                            processed_data
                        )
                        plotter.update(
                            hr_value=hr_value,
                            ecg_samples=ecg_samples,
                        )
                else:
                    print(
                        f"Package {index + 1} discarded "
                        f"(length: {len(processed_data)} bytes)"
                    )

                time.sleep(interval)

            filename = build_output_filename(output_name)
            with open(filename, "wb") as file:
                file.write(concatenated_data)

            print(f"Data saved to {filename}")

    except serial.SerialException as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    finally:
        if ser is not None and ser.is_open:
            ser.close()


def stripspaces(command):
    """Remove spaces from a hex command string."""
    return command.replace(" ", "")


def load_wave_config(base_dir=None, config_path=None):
    """Load waveform definitions from JSON config file."""
    if base_dir is None:
        base_dir = Path.cwd()
    else:
        base_dir = Path(base_dir)

    cfg_path = resolve_gui_config_path(config_path)
    if cfg_path is None and config_path:
        fallback = (base_dir / config_path).resolve()
        if fallback.exists():
            cfg_path = fallback

    if cfg_path is None or not cfg_path.exists():
        return None

    try:
        raw_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        wave_select = raw_cfg.get("channels", {}).get("waves", [])
        if wave_select:
            return wave_select
    except Exception:
        pass

    return None


def print_terminal_output(index, processed_data, wave_defs=None):
    """Print formatted waveform data to terminal."""
    hr_value, ecg_samples = extract_first_hr_and_ecg(processed_data)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(
        f"\n[Package {index + 1}] {now} | Length: {len(processed_data)} bytes"
    )

    if hr_value is not None:
        print(f"  Heart Rate (first): {hr_value} bpm")

    if ecg_samples:
        sample_count = len(ecg_samples)
        min_sample = min(ecg_samples)
        max_sample = max(ecg_samples)
        avg_sample = sum(ecg_samples) / sample_count if sample_count else 0
        print(
            f"  Waveform (first): {sample_count} samples | "
            f"min={min_sample}, max={max_sample}, avg={avg_sample:.1f}"
        )
        if sample_count <= 20:
            print(f"    Samples: {ecg_samples}")
        else:
            print(f"    First 10: {ecg_samples[:10]}")
            print(f"    Last 10:  {ecg_samples[-10:]}")


def _resolve_alarm_frames_from_config(config_path):
    """Return alarm start/stop frame lists from protocol config keys."""

    resolved_path = resolve_gui_config_path(config_path)
    if resolved_path is None:
        raise FileNotFoundError(f"config not found: {config_path}")

    def _pick(config_data, *paths):
        for path in paths:
            cur = config_data
            ok = True
            for key in path:
                if not isinstance(cur, dict) or key not in cur:
                    ok = False
                    break
                cur = cur[key]
            if ok and isinstance(cur, str) and cur.strip():
                return stripspaces(cur)
        return ""

    cfg = json.loads(Path(resolved_path).read_text(encoding="utf-8"))
    xmit_status_hex = _pick(
        cfg,
        ("protocol", "commands", "alarm_xmit_status_hex"),
        ("protocol", "commands", "alarm_cmd_0_hex"),
    )
    enter_diff_hex = _pick(
        cfg,
        ("protocol", "commands", "alarm_enter_diffmode_hex"),
        ("protocol", "commands", "alarm_cmd_2_hex"),
    )
    exit_diff_hex = _pick(
        cfg,
        ("protocol", "commands", "alarm_exit_diffmode_hex"),
        ("protocol", "commands", "alarm_cmd_3_hex"),
    )

    start_hex = _pick(
        cfg,
        ("protocol", "alarm_start_hex"),
        ("protocol", "commands", "alarm_start_hex"),
    )
    stop_hex = _pick(
        cfg,
        ("protocol", "alarm_stop_hex"),
        ("protocol", "commands", "alarm_stop_hex"),
    )

    start_frames = [frame for frame in (xmit_status_hex, enter_diff_hex) if frame]
    stop_frames = [frame for frame in (exit_diff_hex,) if frame]

    if not start_frames and start_hex:
        start_frames = [start_hex]
    if not stop_frames and stop_hex:
        stop_frames = [stop_hex]

    return start_frames, stop_frames


def run_terminal_simulator(
    port,
    duration_sec,
    wave_defs=None,
    output_name=None,
    baudrate=115200,
    use_rtscts=True,
    alarm_start_frames=None,
    alarm_stop_frames=None,
):
    """Run headless collection, print to terminal, and optionally save DRC file."""
    print(f"Running for {duration_sec} seconds...\n")

    start_param_command = stripspaces(
        "7E31 0000 00E8 FD25 0407 6700 0000 0000 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0001 0A00 0800 0000 0000 BF7E"
    )
    start_waves_command = stripspaces(
        "7E58 0000 00E8 FD58 2708 6700 0000 0001 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0005 0001 0408 09FF 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0045 7E"
    )
    stop_param_command = stripspaces(
        "7E31 0000 00E8 FD33 0607 6700 0000 0000 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0001 0000 0800 0000 0000 C57E"
    )
    stop_waves_command = stripspaces(
        "7E58 0000 00E8 FD35 2808 6700 0000 0001 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0001 0005 0001 FF00 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 000F 7E"
    )

    ser = None
    try:
        ser = serial.Serial(
            port=port,
            baudrate=int(baudrate),
            timeout=5,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            rtscts=bool(use_rtscts),
        )

        ser.write(bytes.fromhex(start_param_command))
        for frame in (alarm_start_frames or []):
            ser.write(bytes.fromhex(stripspaces(frame)))
        ser.write(bytes.fromhex(start_waves_command))

        start_time = time.time()
        package_index = 0
        concatenated_data = bytearray()

        while time.time() - start_time < duration_sec:
            try:
                incoming_data = ser.read_until(bytes([FLAG_CHAR]))

                if len(incoming_data) < 40:
                    incoming_data = ser.read_until(bytes([FLAG_CHAR]))

                processed_data = process_received_data(incoming_data)

                if len(processed_data) > 40:
                    concatenated_data.extend(processed_data)
                    print_terminal_output(
                        package_index,
                        processed_data,
                        wave_defs=wave_defs,
                    )
                    package_index += 1
            except serial.SerialException:
                break

        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"Collection stopped after {elapsed:.1f}s")
        print(f"Total packages received: {package_index}")
        
        if output_name and concatenated_data:
            filename = build_output_filename(output_name)
            with open(filename, "wb") as file:
                file.write(concatenated_data)
            print(f"Data saved to {filename} ({len(concatenated_data)} bytes)")
        
        print("=" * 60)

        ser.write(bytes.fromhex(stop_param_command))
        for frame in (alarm_stop_frames or []):
            ser.write(bytes.fromhex(stripspaces(frame)))
        ser.write(bytes.fromhex(stop_waves_command))

    except serial.SerialException as exc:
        print(f"Serial error: {exc}")
        sys.exit(1)
    finally:
        if ser is not None and ser.is_open:
            ser.close()


def main():
    """Parse CLI arguments and run capture sequence."""
    _startup_log(
        f"pycollect main start frozen={getattr(sys, 'frozen', False)} argv={sys.argv!r}"
    )
    parser = argparse.ArgumentParser(
        description=(
            "Send hexadecimal commands to a serial port "
            "and capture DRC data."
        )
    )
    parser.add_argument(
        "port",
        nargs="?",
        help="Serial port to use, for example COM2",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Send stop command only.",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--gui",
        action="store_true",
        help="Enable live graph (heart rate + ECG waveform).",
    )
    mode_group.add_argument(
        "--qt-gui",
        action="store_true",
        help="Launch interactive Qt GUI with left sidebar controls.",
    )
    mode_group.add_argument(
        "--blind",
        action="store_true",
        help="Force blind collection mode (default behavior).",
    )
    mode_group.add_argument(
        "--terminal-simulator",
        action="store_true",
        help=(
            "Headless mode for simulator: load waveforms from JSON config "
            "and print to terminal."
        ),
    )
    parser.add_argument(
        "--plot-window-sec",
        type=int,
        default=10,
        help="Rolling display window in seconds for GUI mode.",
    )
    parser.add_argument(
        "--plot-refresh-sec",
        type=int,
        default=10,
        help="GUI refresh cadence in seconds.",
    )
    parser.add_argument(
        "--ecg-samples-per-sec",
        type=int,
        default=500,
        help="Approx ECG samples per second for GUI rolling window size.",
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
            "Enable simulator-friendly Qt behavior such as section collapse "
            "and idle auto-close."
        ),
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help=(
            "Auto-stop the Qt GUI capture after this many seconds. "
            "0 disables (default)."
        ),
    )
    parser.add_argument(
        "--debug-stdout",
        action="store_true",
        help="Mirror Qt GUI log lines to stdout for debugging.",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=None,
        help="Override serial baud rate for Qt GUI (19200 or 115200).",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=0,
        help="Optional localhost TCP control port for Qt GUI.",
    )
    parser.add_argument(
        "--no-rtscts",
        action="store_true",
        help="Disable RTS/CTS hardware flow control for Qt GUI.",
    )
    parser.add_argument(
        "--with-alarms",
        action="store_true",
        help=(
            "Enable protocol alarm request frames in headless "
            "--terminal-simulator mode."
        ),
    )
    parser.add_argument(
        "--config",
        default="config/pycollect_gui_config.json",
        help="Path to JSON config file (for --terminal-simulator mode).",
    )

    args = parser.parse_args()

    if args.qt_gui:
        gui_args = []
        if args.port:
            gui_args.extend(["--port", args.port])
        if args.output:
            gui_args.extend(["--output", args.output])
        if args.simulation_mode:
            gui_args.append("--simulation-mode")
        if args.duration and args.duration > 0:
            gui_args.extend(["--duration", str(args.duration)])
        if args.debug_stdout:
            gui_args.append("--debug-stdout")
        if args.baud and args.baud in (19200, 115200):
            gui_args.extend(["--baud", str(args.baud)])
        if args.control_port and args.control_port > 0:
            gui_args.extend(["--control-port", str(args.control_port)])
        if args.no_rtscts:
            gui_args.append("--no-rtscts")

        if getattr(sys, "frozen", False):
            _startup_log(f"qt gui frozen in-process args={gui_args!r}")
            previous_argv = sys.argv[:]
            try:
                from pycollect_qt_gui import main as qt_main

                sys.argv = [previous_argv[0]] + gui_args
                qt_main()
            finally:
                sys.argv = previous_argv
        else:
            gui_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "pycollect_qt_gui.py",
            )
            command = [sys.executable, gui_script] + gui_args
            _startup_log(f"qt gui subprocess command={command!r}")
            subprocess.run(command, check=False)
        return

    if args.terminal_simulator:
        if not args.port:
            parser.error("port is required for --terminal-simulator mode")
        resolved_cfg = resolve_gui_config_path(args.config)
        if resolved_cfg is None:
            parser.error(
                "config not found. looked for "
                f"{args.config!r} across runtime paths (cwd, install dir, "
                "config/, LocalAppData\\pyCollect)"
            )
        wave_defs = load_wave_config(
            base_dir=os.getcwd(),
            config_path=str(resolved_cfg),
        )
        cli_baud = int(args.baud) if args.baud in (19200, 115200) else 115200
        cli_use_rtscts = not args.no_rtscts
        alarm_start_frames = []
        alarm_stop_frames = []
        if args.with_alarms:
            try:
                alarm_start_frames, alarm_stop_frames = (
                    _resolve_alarm_frames_from_config(str(resolved_cfg))
                )
                print(
                    "Alarm requests enabled: "
                    f"start={len(alarm_start_frames)} "
                    f"stop={len(alarm_stop_frames)}"
                )
            except Exception as exc:
                parser.error(
                    "failed to load alarm frames from config "
                    f"{args.config}: {exc}"
                )
        print(f"Terminal simulator mode on {args.port}")
        if wave_defs:
            print(f"Loaded {len(wave_defs)} waveform definitions from config")
        run_terminal_simulator(
            port=args.port,
            duration_sec=args.duration if args.duration > 0 else 60,
            wave_defs=wave_defs,
            output_name=args.output,
            baudrate=cli_baud,
            use_rtscts=cli_use_rtscts,
            alarm_start_frames=alarm_start_frames,
            alarm_stop_frames=alarm_stop_frames,
        )
        return

    if not args.port:
        parser.error("port is required unless --qt-gui or --terminal-simulator is used")

    cli_baud = int(args.baud) if args.baud in (19200, 115200) else 115200
    cli_use_rtscts = not args.no_rtscts

    use_gui = args.gui and not args.blind
    if use_gui:
        hr_window_points = max(1, args.plot_window_sec)
        ecg_window_samples = max(
            100,
            args.plot_window_sec * max(1, args.ecg_samples_per_sec),
        )
        refresh_every = max(1, args.plot_refresh_sec)
        plotter = LiveMonitorPlot(
            hr_window_points=hr_window_points,
            ecg_window_samples=ecg_window_samples,
            refresh_interval_sec=refresh_every,
        )
    else:
        plotter = None

    start_param_displ_command = stripspaces(
        "7E31 0000 00E8 FD25 0407 6700 0000 0000 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0001 0A00 0800 0000 0000 BF7E"
    )
    stop_param_displ_command = stripspaces(
        "7E31 0000 00E8 FD33 0607 6700 0000 0000 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0001 0000 0800 0000 0000 C57E"
    )
    start_waves_command = stripspaces(
        "7E58 0000 00E8 FD58 2708 6700 0000 0001 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0005 0001 0408 09FF 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0045 7E"
    )
    stop_waves_command = stripspaces(
        "7E58 0000 00E8 FD35 2808 6700 0000 0001 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0001 0005 0001 FF00 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0000 0000 0000 0000 0000 000F 7E"
    )

    if not args.stop:
        send_hex_command(
            args.port,
            bytes.fromhex(start_param_displ_command),
            "start",
            10,
            6,
            plotter=plotter,
            output_name=args.output,
            baudrate=cli_baud,
            use_rtscts=cli_use_rtscts,
        )
        send_hex_command(
            args.port,
            bytes.fromhex(start_waves_command),
            "start",
            1,
            60,
            plotter=plotter,
            output_name=args.output,
            baudrate=cli_baud,
            use_rtscts=cli_use_rtscts,
        )

    send_hex_command(
        args.port,
        bytes.fromhex(stop_param_displ_command),
        "stop",
        1,
        1,
        baudrate=cli_baud,
        use_rtscts=cli_use_rtscts,
    )
    send_hex_command(
        args.port,
        bytes.fromhex(stop_waves_command),
        "stop",
        1,
        1,
        baudrate=cli_baud,
        use_rtscts=cli_use_rtscts,
    )

    if plotter is not None:
        try:
            plotter.plt.show(block=True)
        finally:
            plotter.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _startup_log("FATAL\n" + traceback.format_exc())
        raise
