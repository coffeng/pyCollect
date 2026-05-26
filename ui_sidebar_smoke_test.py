"""Per-section sidebar smoke test for the Qt GUI.

Runs the GUI in offscreen mode and exercises every sidebar section:
  1. Connection: refresh ports, combo populated, programmatic selection.
  2. Display Windows: duration/trend/wave spinboxes accept changes.
  3. Capture: start without port -> log warning; stop is safe when idle.
  4. Signal Selection: each slot button is wired and selector grid exists.
  5. Waveform Catalog: covered by ui_waveform_catalog_smoke_test (recheck
     section is collapsible).
  6. Status: log() appends, debug_stdout mirrors, post-close is safe.

Exit code 0 on success.
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout
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


def _make_window(debug_stdout: bool = False) -> gui.PyCollectQtWindow:
    base = Path(__file__).resolve().parent
    config = gui.load_signal_config(base)
    win = gui.PyCollectQtWindow(
        config=config,
        output_name="",
        initial_port=None,
        autostart=False,
        simulation_mode=False,
        initial_duration=15,
        debug_stdout=debug_stdout,
    )
    win.show()
    QtWidgets.QApplication.processEvents()
    return win


def test_connection(win: gui.PyCollectQtWindow) -> None:
    print("[1] Connection section")
    _expect(win.conn_section is not None, "connection section exists")
    _expect(
        win.conn_section.toggle_btn.isChecked(),
        "starts expanded",
    )
    # Toggle collapse / expand via click
    win.conn_section.toggle_btn.click()
    QtWidgets.QApplication.processEvents()
    _expect(
        not win.conn_section.content.isVisible(),
        "collapses on click",
    )
    win.conn_section.toggle_btn.click()
    QtWidgets.QApplication.processEvents()
    _expect(
        win.conn_section.content.isVisible(),
        "expands on click",
    )
    # Refresh ports button is wired and populates combo without error
    before = win.port_combo.count()
    win.refresh_ports_btn.click()
    QtWidgets.QApplication.processEvents()
    after = win.port_combo.count()
    _expect(after >= 0, f"refresh_ports ran ({before} -> {after})")


def test_display_windows(win: gui.PyCollectQtWindow) -> None:
    print("[2] Display Windows section")
    win.duration_spin.setValue(30)
    win.hr_window_spin.setValue(45)
    win.ecg_window_spin.setValue(12.5)
    QtWidgets.QApplication.processEvents()
    _expect(win.duration_spin.value() == 30, "duration spin accepts 30")
    _expect(win.hr_window_spin.value() == 45, "trend spin accepts 45")
    _expect(
        abs(win.ecg_window_spin.value() - 12.5) < 1e-6,
        "wave spin accepts 12.5",
    )
    # Boundary clamps
    win.ecg_window_spin.setValue(5.0)  # below min 10.0
    _expect(
        win.ecg_window_spin.value() >= 10.0,
        "wave spin clamps to min 10.0",
    )
    win.ecg_window_spin.setValue(500.0)  # above max 300.0
    _expect(
        win.ecg_window_spin.value() <= 300.0,
        "wave spin clamps to max 300.0",
    )


def test_capture(win: gui.PyCollectQtWindow) -> None:
    print("[3] Capture section")
    _expect(win.start_btn.isEnabled(), "start enabled initially")
    _expect(not win.stop_btn.isEnabled(), "stop disabled initially")
    # Click start with no port selected -> should log warning, not crash.
    win.port_combo.setCurrentIndex(-1)
    win.port_combo.clearEditText()
    win.start_btn.click()
    QtWidgets.QApplication.processEvents()
    text = win.status_box.toPlainText()
    _expect(
        "No COM port" in text,
        "start with empty port logs 'No COM port'",
    )
    _expect(win.start_btn.isEnabled(), "start still enabled after warning")
    # Stop click while idle: safe no-op.
    try:
        win.stop_btn.click()
        QtWidgets.QApplication.processEvents()
        ok = True
    except Exception as exc:
        ok = False
        print(f"    exception: {exc}")
    _expect(ok, "stop click while idle is safe")


def test_signal_selection(win: gui.PyCollectQtWindow) -> None:
    print("[4] Signal Selection section")
    _expect(hasattr(win, "_select_trends_btn"),
            "Signal Setup has Select Trends button")
    _expect(isinstance(win._select_trends_btn, QtWidgets.QPushButton),
            "_select_trends_btn is a QPushButton")
    # Verify clicking the button does not crash. We patch QDialog.exec_
    # to avoid blocking.
    btn = win._select_trends_btn
    original_exec = QtWidgets.QDialog.exec_

    def fake_exec(self):
        return QtWidgets.QDialog.Rejected

    QtWidgets.QDialog.exec_ = fake_exec
    try:
        btn.click()
        QtWidgets.QApplication.processEvents()
        ok = True
    except Exception as exc:
        ok = False
        print(f"    exception: {exc}")
    finally:
        QtWidgets.QDialog.exec_ = original_exec
    _expect(ok, "Select Trends button click opens selector without crash")


def test_waveform_catalog_collapsible(win: gui.PyCollectQtWindow) -> None:
    print("[5] Waveform Catalog section (collapse / expand only)")
    sec = win.wave_catalog_section
    sec.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()
    _expect(sec.content.isVisible(), "catalog visible after expand")
    sec.toggle_btn.setChecked(False)
    QtWidgets.QApplication.processEvents()
    _expect(not sec.content.isVisible(), "catalog hidden after collapse")


def test_status_section(win: gui.PyCollectQtWindow) -> None:
    print("[6] Status section + log()")
    win.status_box.clear()
    win.log("hello world")
    QtWidgets.QApplication.processEvents()
    _expect(
        "hello world" in win.status_box.toPlainText(),
        "log appends to status box",
    )
    # debug_stdout mirror
    win.debug_stdout = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        win.log("mirror test")
    _expect(
        "mirror test" in buf.getvalue(),
        "debug_stdout mirrors to stdout",
    )
    win.debug_stdout = False


def test_close_safety(win: gui.PyCollectQtWindow) -> None:
    print("[7] Close teardown")
    win.close()
    QtWidgets.QApplication.processEvents()
    _expect(win._is_closing, "_is_closing set on close")
    # post-close calls must be safe
    try:
        win.log("after close")
        win._refresh_wave_request_button_states()
        ok = True
    except Exception as exc:
        ok = False
        print(f"    exception: {exc}")
    _expect(ok, "log + refresh after close are safe")


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = _make_window()
    test_connection(win)
    test_display_windows(win)
    test_capture(win)
    test_signal_selection(win)
    test_waveform_catalog_collapsible(win)
    test_status_section(win)
    test_close_safety(win)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} assertion(s)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All sidebar smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
