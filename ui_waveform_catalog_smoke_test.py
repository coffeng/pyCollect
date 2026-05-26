"""Headless smoke test for the waveform request catalog and button color
state machine.

Boots the Qt GUI in offscreen mode (no monitor needed), simulates clicks on
catalog buttons, forces last-received timestamps to exercise all 5 states
(blue/green/yellow/red/default), and asserts the resulting button color
matches the documented state machine.

Exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets  # noqa: E402

import pycollect_qt_gui as gui  # noqa: E402


FAILURES: list[str] = []


def _expect(cond: bool, msg: str) -> None:
    if cond:
        print(f"  PASS: {msg}")
    else:
        print(f"  FAIL: {msg}")
        FAILURES.append(msg)


def _make_window() -> gui.PyCollectQtWindow:
    base = Path(__file__).resolve().parent
    config = gui.load_signal_config(base)
    win = gui.PyCollectQtWindow(
        config=config,
        output_name="",
        initial_port=None,
        autostart=False,
        simulation_mode=False,
        initial_duration=30,
        debug_stdout=False,
    )
    win.show()
    QtWidgets.QApplication.processEvents()
    return win


def _state(win: gui.PyCollectQtWindow, row_id: int) -> str:
    win._apply_wave_request_button_style(row_id)
    QtWidgets.QApplication.processEvents()
    btn = win.wave_request_buttons[row_id]
    return btn.property("color_state") or "default"


def test_catalog_visibility(win: gui.PyCollectQtWindow) -> None:
    print("[1] Catalog section visibility/scrollable")
    sec = win.wave_catalog_section
    _expect(sec is not None, "catalog section exists")
    _expect(len(win.wave_request_buttons) > 0, "buttons populated")
    # Expand the section and verify children are visible.
    sec.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()
    _expect(sec.content.isVisible(), "catalog expands on click")
    sec.toggle_btn.setChecked(False)
    QtWidgets.QApplication.processEvents()
    _expect(not sec.content.isVisible(), "catalog collapses on click")
    sec.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()


def test_displayed_rows_selection_rules(win: gui.PyCollectQtWindow) -> None:
    print("[2] Displayed rows follow active-appending selection rules")
    displayed = win._displayed_wave_row_ids()
    _expect(len(displayed) > 0, "have at least one displayed row")

    # Rule A: when not actively appending, displayed rows can be toggled.
    for row_id in displayed:
        _expect(
            row_id in win.wave_requested_rows,
            f"displayed row #{row_id} auto-requested",
        )
        btn = win.wave_request_buttons[row_id]
        btn.click()  # simulated uncheck
        QtWidgets.QApplication.processEvents()
        _expect(
            row_id not in win.wave_requested_rows,
            f"displayed row #{row_id} can be unrequested when idle",
        )
        _expect(
            not btn.isChecked(),
            f"displayed row #{row_id} button can uncheck when idle",
        )
        btn.click()  # simulated re-check
        QtWidgets.QApplication.processEvents()
        _expect(
            row_id in win.wave_requested_rows,
            f"displayed row #{row_id} can be re-requested when idle",
        )

    # Rule B: when actively appending and row is non-red, displayed rows
    # are protected from unrequest.
    row_id = sorted(displayed)[0]
    btn = win.wave_request_buttons[row_id]
    prev_worker = win.worker
    prev_file_state = win.current_file_state
    prev_capture_started = win.capture_started_monotonic

    class _FakeWorker:
        def isRunning(self):
            return True

        def update_requested_wave_rows(self, _rows):
            return None

        def update_wave_defs(self, _wave_defs):
            return None

    try:
        win.current_file_state = "blue"
        win.worker = _FakeWorker()
        win.wave_requested_rows.add(row_id)
        win.wave_last_received_at[row_id] = time.monotonic()

        btn.click()  # attempt uncheck while green/active
        QtWidgets.QApplication.processEvents()
        _expect(
            row_id in win.wave_requested_rows,
            "displayed row stays requested while active and receiving",
        )
        _expect(
            btn.isChecked(),
            "displayed row button stays checked while active and receiving",
        )

        # Rule C: during active appending, red/missing displayed rows can be
        # unrequested.
        win.capture_started_monotonic = (
            time.monotonic() - (win.WAVE_REQUEST_TIMEOUT_SEC + 1.0)
        )
        win.wave_last_received_at.pop(row_id, None)
        _expect(
            win._wave_request_button_state(row_id) == "red",
            "displayed row transitions to red when missing during active append",
        )

        btn.click()  # attempt uncheck while red/active
        QtWidgets.QApplication.processEvents()
        _expect(
            row_id not in win.wave_requested_rows,
            "displayed red row can be unrequested while active",
        )
    finally:
        win.worker = prev_worker
        win.current_file_state = prev_file_state
        win.capture_started_monotonic = prev_capture_started


def test_color_states(win: gui.PyCollectQtWindow) -> None:
    print("[3] Color state machine (blue/green/yellow/red/default)")
    # Keep this test in idle mode so state colors map to pure request/receipt.
    prev_worker = win.worker
    prev_file_state = win.current_file_state
    win.worker = None
    win.current_file_state = "closed"

    # Pick a non-displayed row for safe toggling.
    displayed = win._displayed_wave_row_ids()
    candidates = [
        rid for rid in win.wave_request_buttons if rid not in displayed
    ]
    _expect(len(candidates) >= 1, "have a non-displayed row to test")
    if not candidates:
        win.worker = prev_worker
        win.current_file_state = prev_file_state
        return
    row_id = candidates[0]

    # default: not requested, never received.
    win.wave_requested_rows.discard(row_id)
    win.wave_last_received_at.pop(row_id, None)
    _expect(_state(win, row_id) == "default", "default state")

    # blue: requested, never received.
    win.wave_request_buttons[row_id].click()
    QtWidgets.QApplication.processEvents()
    win.wave_last_received_at.pop(row_id, None)
    _expect(
        row_id in win.wave_requested_rows,
        f"click sets row #{row_id} requested",
    )
    _expect(_state(win, row_id) == "blue", "blue state (requested, no data)")

    # green: requested, recently received.
    win.wave_last_received_at[row_id] = time.monotonic()
    _expect(
        _state(win, row_id) == "green",
        "green state (requested + receiving)",
    )

    # red: requested, last received older than timeout.
    win.wave_last_received_at[row_id] = (
        time.monotonic() - (win.WAVE_REQUEST_TIMEOUT_SEC + 1.0)
    )
    _expect(
        _state(win, row_id) == "red",
        "red state (requested, timed out)",
    )

    # yellow: not requested but recently received.
    win.wave_request_buttons[row_id].click()  # uncheck
    QtWidgets.QApplication.processEvents()
    _expect(
        row_id not in win.wave_requested_rows,
        "second click clears request",
    )
    win.wave_last_received_at[row_id] = time.monotonic()
    _expect(
        _state(win, row_id) == "yellow",
        "yellow state (received but not requested)",
    )

    # back to default after staleness with no request.
    win.wave_last_received_at[row_id] = (
        time.monotonic() - (win.WAVE_REQUEST_TIMEOUT_SEC + 1.0)
    )
    _expect(
        _state(win, row_id) == "default",
        "default state (not requested, stale data)",
    )

    win.worker = prev_worker
    win.current_file_state = prev_file_state


def test_persistence_of_requested(win: gui.PyCollectQtWindow) -> None:
    print("[4] _save_runtime_config does not crash with requested state")
    # Just exercise save path; the file is written next to the config.
    try:
        win._save_runtime_config()
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"    exception: {exc}")
    _expect(ok, "save_runtime_config runs without error")


def test_close_teardown(win: gui.PyCollectQtWindow) -> None:
    print("[5] Close teardown is safe (no RuntimeError from late signals)")
    win.close()
    QtWidgets.QApplication.processEvents()
    _expect(win._is_closing, "_is_closing set on close")
    # Calling refresh post-close must be a no-op (no exception).
    try:
        win._refresh_wave_request_button_states()
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"    exception: {exc}")
    _expect(ok, "refresh after close is no-op")


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = _make_window()
    test_catalog_visibility(win)
    test_displayed_rows_selection_rules(win)
    test_color_states(win)
    test_persistence_of_requested(win)
    test_close_teardown(win)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} assertion(s)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All catalog + button coloring smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
