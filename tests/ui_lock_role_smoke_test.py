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
        ("capture_section", "Monitoring Control"),
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
    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("capture_section", "Monitoring Control"),
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
        editable = sec._get_editable_widgets()
        if editable:
            _expect(not editable[0].isEnabled(),
                    f"{name} first editable widget disabled when locked")

        sec.set_locked(False)
        QtWidgets.QApplication.processEvents()
        _expect(not sec.is_locked, f"{name} unlocks back")
        if editable:
            _expect(editable[0].isEnabled(),
                    f"{name} first editable widget re-enabled after unlock")


# ── 5. Locked section cannot be expanded ─────────────────────────

def test_locked_section_cannot_expand(win: gui.PyCollectQtWindow) -> None:
    print("[5] Locked section cannot be expanded")
    sec = win.conn_section

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

    win.conn_section.toggle_btn.setChecked(False)
    win.view_section.toggle_btn.setChecked(False)
    win.capture_section.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()

    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    _expect(win.conn_section.is_locked, "collapsed conn_section got locked")
    _expect(win.view_section.is_locked, "collapsed view_section got locked")
    _expect(not win.capture_section.is_locked, "expanded capture_section not locked")
    _expect("\U0001f512" in win._lock_btn.text(), "lock button shows lock after locking")

    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    for s in win._all_lockable_sections():
        _expect(not s.is_locked, f"{s.title} unlocked after second toggle")
    _expect("\U0001f513" in win._lock_btn.text(), "lock button shows unlock after unlocking")

    win.conn_section.toggle_btn.setChecked(True)
    win.view_section.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()


# ── 7. Lock persistence to config ────────────────────────────────

def test_lock_persistence(win: gui.PyCollectQtWindow) -> None:
    print("[7] Lock persistence to config")

    for s in win._all_lockable_sections():
        s.set_locked(False)
    QtWidgets.QApplication.processEvents()

    win.conn_section.toggle_btn.setChecked(False)
    QtWidgets.QApplication.processEvents()
    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    locked_titles = cfg.get("ui", {}).get("locked_sections", [])
    _expect("Monitor Connection" in locked_titles,
            "'Monitor Connection' in locked_sections")

    win._toggle_all_locks()
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    locked_titles = cfg.get("ui", {}).get("locked_sections", [])
    _expect(locked_titles == [], "locked_sections empty after unlock")

    win.conn_section.toggle_btn.setChecked(True)
    QtWidgets.QApplication.processEvents()


# ── 8. Left-aligned section headers ──────────────────────────────

def test_left_aligned_headers(win: gui.PyCollectQtWindow) -> None:
    print("[8] Left-aligned section headers")
    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("capture_section", "Monitoring Control"),
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


def test_section_locking(win: gui.PyCollectQtWindow) -> None:
    print("[2] Section locking infrastructure")

    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("capture_section", "Monitoring Control"),
    ]:
        sec = getattr(win, attr, None)
        _expect(sec is not None, f"{name} section exists")
        _expect(sec.lockable, f"{name} is lockable")
        _expect(hasattr(sec, "lock_btn"), f"{name} has lock_btn")

        # Start unlocked
        sec.set_locked(False)
        QtWidgets.QApplication.processEvents()
        _expect(not sec.is_locked, f"{name} starts unlocked")
        _expect("🔓" in sec.lock_btn.text(), f"{name} shows open lock icon")

        # Lock it
        sec.set_locked(True)
        QtWidgets.QApplication.processEvents()
        _expect(sec.is_locked, f"{name} set_locked(True) works")
        _expect("🔒" in sec.lock_btn.text(), f"{name} shows closed lock icon")

        # Verify content widgets are disabled when locked
        editable = sec._get_editable_widgets()
        if editable:
            _expect(
                not editable[0].isEnabled(),
                f"{name} first editable widget disabled when locked",
            )

        # Unlock
        sec.set_locked(False)
        QtWidgets.QApplication.processEvents()
        _expect(not sec.is_locked, f"{name} unlocks back")
        if editable:
            _expect(
                editable[0].isEnabled(),
                f"{name} first editable widget re-enabled after unlock",
            )


# ── 3. Section lock persistence to config JSON ────────────────────

def test_lock_persistence(win: gui.PyCollectQtWindow) -> None:
    print("[3] Section lock persistence")

    # Lock monitor_connection
    win.conn_section.set_locked(True)
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    locks = cfg.get("ui", {}).get("section_locks", {})
    _expect(
        locks.get("monitor_connection") is True,
        "monitor_connection lock persisted as True",
    )

    # Unlock it
    win.conn_section.set_locked(False)
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    locks = cfg.get("ui", {}).get("section_locks", {})
    _expect(
        locks.get("monitor_connection") is False,
        "monitor_connection lock persisted as False after unlock",
    )


# ── 4. Left-aligned section headers ───────────────────────────────

def test_left_aligned_headers(win: gui.PyCollectQtWindow) -> None:
    print("[4] Left-aligned section headers")

    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("capture_section", "Monitoring Control"),
    ]:
        sec = getattr(win, attr, None)
        if sec is None:
            continue
        style = sec.toggle_btn.styleSheet()
        _expect("text-align: left" in style, f"{name} header is left-aligned")

        policy = sec.toggle_btn.sizePolicy()
        _expect(
            policy.horizontalPolicy() == QtWidgets.QSizePolicy.Expanding,
            f"{name} toggle_btn has Expanding horizontal policy",
        )


# ── 5. User role combo ────────────────────────────────────────────

def test_user_role_combo(win: gui.PyCollectQtWindow) -> None:
    print("[5] User role combo")

    combo = win.user_role_combo
    _expect(combo is not None, "user_role_combo exists")

    items = [combo.itemText(i) for i in range(combo.count())]
    _expect("Administrator" in items, "'Administrator' in options")
    _expect("Reviewer" in items, "'Reviewer' in options")
    _expect("Recorded" in items, "'Recorded' in options")


# ── 6. User role: Administrator allows lock controls ──────────────

def test_role_administrator(win: gui.PyCollectQtWindow) -> None:
    print("[6] Role: Administrator")

    combo = win.user_role_combo
    combo.setCurrentText("Administrator")
    QtWidgets.QApplication.processEvents()

    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("capture_section", "Monitoring Control"),
    ]:
        sec = getattr(win, attr, None)
        if sec is None:
            continue
        _expect(sec.lock_btn.isEnabled(), f"{name} lock_btn enabled for Admin")


# ── 7. User role: Reviewer forces lock on monitor-comm sections ───

def test_role_reviewer(win: gui.PyCollectQtWindow) -> None:
    print("[7] Role: Reviewer")

    # Ensure all sections unlocked first
    win.conn_section.set_locked(False)
    win.view_section.set_locked(False)
    win.capture_section.set_locked(False)
    QtWidgets.QApplication.processEvents()

    combo = win.user_role_combo
    combo.setCurrentText("Reviewer")
    QtWidgets.QApplication.processEvents()

    # Monitor comm sections should be force-locked
    _expect(
        win.conn_section.is_locked,
        "Monitor Connection force-locked for Reviewer",
    )
    _expect(
        win.capture_section.is_locked,
        "Monitoring Control force-locked for Reviewer",
    )

    # All lock buttons should be disabled (greyed)
    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("capture_section", "Monitoring Control"),
    ]:
        sec = getattr(win, attr, None)
        if sec is None:
            continue
        _expect(
            not sec.lock_btn.isEnabled(),
            f"{name} lock_btn disabled for Reviewer",
        )


# ── 8. User role: Recorded disables lock controls ─────────────────

def test_role_recorded(win: gui.PyCollectQtWindow) -> None:
    print("[8] Role: Recorded")

    combo = win.user_role_combo
    combo.setCurrentText("Recorded")
    QtWidgets.QApplication.processEvents()

    for attr, name in [
        ("conn_section", "Monitor Connection"),
        ("view_section", "Session Setup"),
        ("capture_section", "Monitoring Control"),
    ]:
        sec = getattr(win, attr, None)
        if sec is None:
            continue
        _expect(
            not sec.lock_btn.isEnabled(),
            f"{name} lock_btn disabled for Recorded",
        )


# ── 9. User role persistence to config ────────────────────────────

def test_role_persistence(win: gui.PyCollectQtWindow) -> None:
    print("[9] User role persistence")

    combo = win.user_role_combo
    combo.setCurrentText("Reviewer")
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    _expect(cfg.get("user_role") == "Reviewer", "role 'Reviewer' persisted")

    combo.setCurrentText("Administrator")
    QtWidgets.QApplication.processEvents()

    cfg = json.loads(win.config_path.read_text(encoding="utf-8"))
    _expect(cfg.get("user_role") == "Administrator", "role 'Administrator' persisted")


# ── 10. Toggle lock via button click ──────────────────────────────

def test_lock_toggle_click(win: gui.PyCollectQtWindow) -> None:
    print("[10] Lock toggle via button click")

    # Ensure Admin role so lock buttons are enabled
    win.user_role_combo.setCurrentText("Administrator")
    QtWidgets.QApplication.processEvents()

    sec = win.conn_section
    sec.set_locked(False)
    QtWidgets.QApplication.processEvents()
    _expect(not sec.is_locked, "starts unlocked")

    # Click lock button
    sec.lock_btn.click()
    QtWidgets.QApplication.processEvents()
    _expect(sec.is_locked, "locked after button click")

    # Click again to unlock
    sec.lock_btn.click()
    QtWidgets.QApplication.processEvents()
    _expect(not sec.is_locked, "unlocked after second click")


# ── main ───────────────────────────────────────────────────────────

def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = _make_window()

    test_trend_interval_spinner(win)
    test_section_locking(win)
    test_lock_persistence(win)
    test_left_aligned_headers(win)
    test_user_role_combo(win)
    test_role_administrator(win)
    test_role_reviewer(win)
    test_role_recorded(win)
    test_role_persistence(win)
    test_lock_toggle_click(win)

    # ── Cleanup: reset all locks and role so other tests aren't affected ──
    win.user_role_combo.setCurrentText("Administrator")
    QtWidgets.QApplication.processEvents()
    for sec in (win.conn_section, win.view_section, win.capture_section):
        sec.set_locked(False)
    QtWidgets.QApplication.processEvents()

    win.close()
    QtWidgets.QApplication.processEvents()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} assertion(s)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All lock/role/interval smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
