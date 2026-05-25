"""Smoke test for features added 2026-05-25: section locking, trend interval
spinner, user role permissions, and left-aligned section headers.

Runs the Qt GUI in offscreen mode (no monitor needed).
Exit code 0 on success.
"""
from __future__ import annotations

import json
import os
import sys
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


# ── 2. Section locking infrastructure ──────────────────────────────

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
