"""Smoke test for locking and trend interval features.

New lock design (2026-05-26):
  - No per-section lock icons.
  - Single '\U0001f513 Lock collapsed sections' button in the Advanced section.
  - Clicking it locks all currently-collapsed sections (grey header, no expand).
  - Clicking again ('\U0001f512 Unlock all sections') unlocks everything.
  - Persisted to ui.locked_sections in config JSON.

Runs offscreen (no monitor needed). Exit code 0 on all pass.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

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
    base = Path(__file__).resolve().parent.parent / "config"
    config = gui.load_signal_config(base)
    win = gui.PyCollectQtWindow(
        config=config,
        output_name="",
        initial_port=None,
        autostart=False,
        simulation_mode=False,
        initial_duration=15,
        debug_stdout=False,
    )
    win.show()
    QtWidgets.QApplication.processEvents()
    return win


# ── 1. Trend interval spinner ──────────────────────────────────────

def test_trend_interval_spinner(win: gui.PyCollectQtWindow) -> None:
    print("[1] Trend interval spinner")
    spin = win.trend_interval_spin
    _expect(spin is not None, "trend_interval_spin exists")
    _expect(spin.minimum() == 5, f"min is 5 (got {spin.minimum()})")
    _expect(spin.maximum() == 120, f"max is 120 (got {spin.maximum()})")
    _expect(spin.singleStep() == 5, f"step is 5 (got {spin.singleStep()})")
    _expect(spin.suffix() == " sec", f"suffix is ' sec' (got '{spin.suffix()}')")

    # Change value and verify config persistence
    spin.setValue(30)
    QtWidgets.QApplication.processEvents()
    _expect(spin.value() == 30, "accepts value 30")

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    _expect(
        cfg.get("ui", {}).get("trend_interval_sec") == 30,
        "persisted trend_interval_sec=30 to config",
    )

    # Boundary: step-aligned clamping
    spin.setValue(3)  # below min
    _expect(spin.value() >= 5, f"clamps below min (got {spin.value()})")
    spin.setValue(200)  # above max
    _expect(spin.value() <= 120, f"clamps above max (got {spin.value()})")


# ── 2. No per-section lock icons ──────────────────────────────────

def test_no_per_section_lock_buttons(win: gui.PyCollectQtWindow) -> None:
    print("[2] No per-section lock icons")
    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("signal_section", "Signal Setup"),
        ("status_section", "Recorder Output"),
    ]:
        sec = getattr(win, attr, None)
        _expect(sec is not None, f"{name} section exists")
        _expect(not hasattr(sec, "lock_btn"), f"{name} has no lock_btn")
        _expect(not hasattr(sec, "lockable"), f"{name} has no lockable attr")


# ── 3. Lock button in Advanced section ────────────────────────────

def test_lock_btn_in_advanced(win: gui.PyCollectQtWindow) -> None:
    print("[3] Lock button in Advanced section")
    _expect(hasattr(win, "_lock_btn"), "_lock_btn attribute exists on window")
    btn = win._lock_btn
    _expect("\U0001f513" in btn.text() or "\U0001f512" in btn.text(),
            "lock button has lock emoji")
    found = win.advanced_section.content.findChildren(QtWidgets.QPushButton)
    labels = [w.text() for w in found]
    _expect(
        any("\U0001f513" in t or "\U0001f512" in t for t in labels),
        "lock button is inside Advanced section content",
    )


# ── 4. set_locked greys header and disables content ───────────────

def test_set_locked_appearance(win: gui.PyCollectQtWindow) -> None:
    print("[4] set_locked appearance")
    # Test lockable CollapsibleSection instances
    for attr, name in [
        ("view_section", "Session Setup"),
        ("signal_section", "Signal Setup"),
    ]:
        sec = getattr(win, attr, None)
        if sec is None:
            continue

        sec.set_locked(False)
        QtWidgets.QApplication.processEvents()
        _expect(not sec.is_locked, f"{name} starts unlocked")

        sec.set_locked(True)
        QtWidgets.QApplication.processEvents()
        _expect(sec.is_locked, f"{name} set_locked(True) works")
        style = sec.toggle_btn.styleSheet()
        _expect(
            "#888888" in style or "#1a1a1a" in style,
            f"{name} header shows grey when locked",
        )

        sec.set_locked(False)
        QtWidgets.QApplication.processEvents()
        _expect(not sec.is_locked, f"{name} unlocks back")

    # Test stub sections (conn_section, file_save_section)
    for attr, name in [
        ("conn_section", "Monitor Connection"),
    ]:
        sec = getattr(win, attr, None)
        if sec is None:
            continue
        sec.set_locked(False)
        _expect(not sec.is_locked, f"{name} starts unlocked")
        sec.set_locked(True)
        _expect(sec.is_locked, f"{name} set_locked(True) works")
        sec.set_locked(False)


# ── 5. Locked section cannot be expanded ─────────────────────────

def test_locked_section_cannot_expand(win: gui.PyCollectQtWindow) -> None:
    print("[5] Locked section cannot be expanded")
    sec = win.view_section  # use a real CollapsibleSection, not the stub

    sec.toggle_btn.setChecked(False)
    QtWidgets.QApplication.processEvents()
    _expect(not sec.content.isVisible(), "section is collapsed")

    sec.set_locked(True)
    QtWidgets.QApplication.processEvents()

    sec.toggle_btn.click()
    QtWidgets.QApplication.processEvents()
    _expect(not sec.content.isVisible(), "locked section stays collapsed on click")
    _expect(not sec.toggle_btn.isChecked(), "toggle stays unchecked when locked")

    sec.set_locked(False)
    sec.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()


# ── 6. _toggle_all_locks locks collapsed sections ─────────────────

def test_toggle_all_locks(win: gui.PyCollectQtWindow) -> None:
    print("[6] _toggle_all_locks locks collapsed sections")

    for s in win._all_lockable_sections():
        s.set_locked(False)
    QtWidgets.QApplication.processEvents()

    win.view_section.toggle_btn.setChecked(False)
    win.signal_section.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()

    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    _expect(win.view_section.is_locked, "collapsed view_section got locked")
    _expect(not win.signal_section.is_locked, "expanded signal_section not locked")
    _expect("\U0001f512" in win._lock_btn.text(), "lock button shows lock after locking")

    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    for s in win._all_lockable_sections():
        _expect(not s.is_locked, f"{s.title} unlocked after second toggle")
    _expect("\U0001f513" in win._lock_btn.text(), "lock button shows unlock after unlocking")

    win.view_section.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()


# ── 7. Lock persistence to config ────────────────────────────────

def test_lock_persistence(win: gui.PyCollectQtWindow) -> None:
    print("[7] Lock persistence to config")

    for s in win._all_lockable_sections():
        s.set_locked(False)
    QtWidgets.QApplication.processEvents()

    win.view_section.toggle_btn.setChecked(False)
    QtWidgets.QApplication.processEvents()
    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    locked_titles = cfg.get("ui", {}).get("locked_sections", [])
    _expect("Screen Setup" in locked_titles,
            "'Screen Setup' in locked_sections")

    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    locked_titles = cfg.get("ui", {}).get("locked_sections", [])
    _expect(locked_titles == [], "locked_sections empty after unlock")

    win.view_section.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()


# ── 8. Left-aligned section headers ──────────────────────────────

def test_left_aligned_headers(win: gui.PyCollectQtWindow) -> None:
    print("[8] Left-aligned section headers")
    for attr, name in [
        ("view_section", "Session Setup"),
        ("signal_section", "Signal Setup"),
        ("status_section", "Recorder Output"),
    ]:
        sec = getattr(win, attr, None)
        if sec is None:
            continue
        _expect("text-align: left" in sec.toggle_btn.styleSheet(),
                f"{name} header is left-aligned")
        _expect(
            sec.toggle_btn.sizePolicy().horizontalPolicy()
            == QtWidgets.QSizePolicy.Expanding,
            f"{name} toggle_btn has Expanding policy",
        )


# ── main ──────────────────────────────────────────────────────────

def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = _make_window()

    test_trend_interval_spinner(win)
    test_no_per_section_lock_buttons(win)
    test_lock_btn_in_advanced(win)
    test_set_locked_appearance(win)
    test_locked_section_cannot_expand(win)
    test_toggle_all_locks(win)
    test_lock_persistence(win)
    test_left_aligned_headers(win)

    # Cleanup: ensure all unlocked on exit so other tests aren't affected
    for s in win._all_lockable_sections():
        s.set_locked(False)
    win._lock_btn.setText("\U0001f513  Lock collapsed sections")
    win._persist_lock_state()
    QtWidgets.QApplication.processEvents()

    win.close()
    QtWidgets.QApplication.processEvents()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} assertion(s)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All lock/interval smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

