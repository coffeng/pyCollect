"""
Diagnostic: run simulator + headless receiver, capture logs, auto-retry GUI.

Usage:
    python tests/sim_gui_diag.py            # headless only
    python tests/sim_gui_diag.py --gui      # headless first, then GUI
    python tests/sim_gui_diag.py --gui-only # GUI only (skip headless)
"""
import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM_SCRIPT  = ROOT / "code" / "drc_monitor_simulator.py"
PY_SCRIPT   = ROOT / "code" / "pycollect.py"
DRC_FILE    = ROOT / "headless_test.drc"
PY_EXE      = ROOT / ".venv" / "Scripts" / "python.exe"

SIM_PORT    = "COM4"
GUI_PORT    = "COM2"
BAUD        = "115200"
MAX_WAIT_SEC = 15          # seconds to wait for packages before giving up

# ── helpers ──────────────────────────────────────────────────────────────────

def drain(proc, label, lines, stop_event):
    """Read stdout+stderr from a subprocess and collect lines."""
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        lines.append(f"[{label}] {line}")
        print(f"[{label}] {line}", flush=True)
        if stop_event.is_set():
            break


def run_sim(extra_args=()):
    cmd = [
        str(PY_EXE), str(SIM_SCRIPT),
        "--drc", str(DRC_FILE),
        "--port", SIM_PORT,
        "--baud", BAUD,
        "--no-rtscts",
        "--loop",
    ] + list(extra_args)
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(ROOT),
    )


# ── headless receiver (mirrors CollectionWorker exactly) ─────────────────────

def run_headless_receiver(baud=int(BAUD), rtscts=True, duration=MAX_WAIT_SEC):
    """
    Mimic CollectionWorker: open COM2, send START command, read packages.
    Returns (packages_ok, packages_discarded, errors).
    """
    import serial
    sys.path.insert(0, str(ROOT / "code"))
    import pycollect

    START_HEX = (
        "7E31 0000 00E8 FD25 0407 6700 0000 0000 0000 0000 "
        "0000 FF00 0000 0000 0000 0000 0000 0000 0000 0000 "
        "0001 0A00 0800 0000 0000 BF7E"
    )

    print(f"[headless] Opening {GUI_PORT} @ {baud}, rtscts={rtscts}", flush=True)
    ok = discarded = 0
    errors = []
    try:
        ser = serial.Serial(
            port=GUI_PORT, baudrate=baud, timeout=5,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE, rtscts=rtscts,
        )
        print(f"[headless] Port opened OK", flush=True)
        # send start command (mirrors GUI)
        try:
            ser.write(bytes.fromhex(pycollect.stripspaces(START_HEX)))
            print(f"[headless] START command sent", flush=True)
        except Exception as e:
            print(f"[headless] WARN: send START failed: {e}", flush=True)
            errors.append(f"send START: {e}")

        deadline = time.monotonic() + duration
        while time.monotonic() < deadline and (ok + discarded) < 20:
            data = ser.read_until(bytes([pycollect.FLAG_CHAR]))
            if len(data) < 40:
                data = ser.read_until(bytes([pycollect.FLAG_CHAR]))
            processed = pycollect.process_received_data(data)
            if len(processed) > 40:
                ok += 1
                print(f"[headless] Package {ok} OK ({len(processed)} bytes)", flush=True)
            else:
                discarded += 1
                print(f"[headless] Package discarded (raw={len(data)}, proc={len(processed)})", flush=True)
        ser.close()
    except Exception as e:
        print(f"[headless] ERROR: {e}", flush=True)
        errors.append(str(e))
    return ok, discarded, errors


# ── GUI run ───────────────────────────────────────────────────────────────────

def run_gui_process(timeout_sec=MAX_WAIT_SEC + 5):
    """Launch pycollect.py --qt-gui, capture debug output, kill after timeout."""
    cmd = [
        str(PY_EXE), str(PY_SCRIPT),
        "--qt-gui", GUI_PORT,
        "--baud", BAUD,
        "--output", str(ROOT / "output" / "diag_record.drc"),
        "--simulation-mode",
        "--debug-stdout",
        "--duration", str(MAX_WAIT_SEC),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(ROOT),
    )
    lines = []
    stop = threading.Event()
    t = threading.Thread(target=drain, args=(proc, "GUI", lines, stop), daemon=True)
    t.start()

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    if proc.poll() is None:
        print("[GUI] Timeout reached — closing GUI", flush=True)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    stop.set()
    t.join(timeout=3)
    return lines, proc.returncode


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gui",      action="store_true", help="Also run GUI after headless")
    ap.add_argument("--gui-only", action="store_true", help="Only run GUI (skip headless)")
    args = ap.parse_args()

    if not DRC_FILE.exists():
        print(f"ERROR: DRC not found: {DRC_FILE}"); sys.exit(1)

    max_retries = 5

    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*60}")
        print(f" ATTEMPT {attempt}/{max_retries}")
        print(f"{'='*60}\n")

        # ── start simulator ──────────────────────────────────────────
        sim = run_sim()
        sim_lines = []
        sim_stop = threading.Event()
        sim_thread = threading.Thread(
            target=drain, args=(sim, "SIM", sim_lines, sim_stop), daemon=True
        )
        sim_thread.start()
        time.sleep(1.0)   # give simulator a moment to open COM4

        success = False

        # ── headless phase ───────────────────────────────────────────
        if not args.gui_only:
            print("\n--- HEADLESS RECEIVER (rtscts=True) ---", flush=True)
            ok, disc, errs = run_headless_receiver(rtscts=True)
            print(f"\nHeadless result: ok={ok}  discarded={disc}  errors={errs}", flush=True)

            if ok == 0 and errs:
                print("\n--- RETRY HEADLESS (rtscts=False) ---", flush=True)
                ok2, disc2, errs2 = run_headless_receiver(rtscts=False)
                print(f"Headless (no rtscts): ok={ok2}  discarded={disc2}  errors={errs2}", flush=True)
                if ok2 > 0:
                    print("FIX NEEDED: GUI CollectionWorker should open with rtscts=False")
                ok, disc, errs = ok2, disc2, errs2

            success = ok > 0

        # ── GUI phase ────────────────────────────────────────────────
        if args.gui or args.gui_only:
            print("\n--- GUI PROCESS ---", flush=True)
            gui_lines, rc = run_gui_process()
            print(f"\nGUI exit code: {rc}", flush=True)
            ok_gui = sum(1 for l in gui_lines if "Package" in l and "bytes" in l)
            disc_gui = sum(1 for l in gui_lines if "discarded" in l)
            err_gui  = [l for l in gui_lines if "error" in l.lower() or "Error" in l]
            print(f"GUI packages ok={ok_gui}  discarded={disc_gui}", flush=True)
            if err_gui:
                print("GUI errors:", flush=True)
                for l in err_gui:
                    print(f"  {l}", flush=True)
            success = success or ok_gui > 0

        # ── stop simulator ───────────────────────────────────────────
        sim_stop.set()
        sim.terminate()
        try:
            sim.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sim.kill()
        sim_thread.join(timeout=3)

        print(f"\n--- SIM OUTPUT (last 10 lines) ---", flush=True)
        for l in sim_lines[-10:]:
            print(l, flush=True)

        if success:
            print(f"\n✓ SUCCESS on attempt {attempt}", flush=True)
            sys.exit(0)
        else:
            print(f"\n✗ FAILED attempt {attempt} — analysing...", flush=True)
            # Check specific known failure patterns and report guidance
            if any("rtscts" in l for l in sim_lines):
                print("  SIM: rtscts setting visible in output", flush=True)
            if any("Access" in l or "PermissionError" in l for l in sim_lines):
                print("  SIM: COM4 port access error!", flush=True)
            if attempt < max_retries:
                print(f"  Waiting 2s before retry...", flush=True)
                time.sleep(2)

    print(f"\n✗ All {max_retries} attempts failed.", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
