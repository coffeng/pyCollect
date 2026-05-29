"""Smoke test for the Notes/Markers feature (PS_COLLECT_UI_009 / PS_COLLECT_UI_010).

Tests:
  1. CaseNotesManager: insert, edit, delete, save, load roundtrip.
  2. CaseNotesManager: disabled config, empty config, template list.
  3. GUI integration: notes section exists, insert button, template menu,
     delete button, table widget.

Exit code 0 on success.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from PyQt5 import QtWidgets  # noqa: E402

import pycollect_qt_gui as gui  # noqa: E402
from notes_manager import CaseNotesManager  # noqa: E402


FAILURES: list[str] = []


def _expect(cond: bool, msg: str) -> None:
    if cond:
        print(f"  PASS: {msg}")
    else:
        print(f"  FAIL: {msg}")
        FAILURES.append(msg)


# ── CaseNotesManager unit tests ──────────────────────────────────────

def test_insert_edit_delete():
    print("[1] Insert / edit / delete")
    nm = CaseNotesManager({"enabled": True})
    nm.start_session(Path(tempfile.mkdtemp()) / "test.drc")

    n1 = nm.insert_note("First note")
    n2 = nm.insert_note("Second note", monitor_time_unix=1748500000)
    _expect(nm.note_count() == 2, "two notes inserted")
    _expect(n1["time_source"] == "pc", "first note uses PC time")
    _expect(n2["time_source"] == "monitor", "second note uses monitor time")
    _expect("2025" in n2["display_time"] or "2026" in n2["display_time"],
            "monitor timestamp converts to local date")

    nm.update_note_text(0, "Updated first")
    _expect(nm.get_note(0)["text"] == "Updated first", "text updated")

    nm.delete_note(1)
    _expect(nm.note_count() == 1, "one note after delete")
    _expect(nm.get_note(0)["text"] == "Updated first", "correct note remains")


def test_save_load_roundtrip():
    print("[2] Save / load roundtrip")
    tmpdir = Path(tempfile.mkdtemp())
    drc = tmpdir / "roundtrip.drc"
    drc.write_bytes(b"fake")

    nm = CaseNotesManager({"enabled": True})
    nm.start_session(drc)
    nm.insert_note("Alpha note")
    nm.insert_note("Beta note")
    nm.end_session()

    sidecar = drc.with_suffix(".txt")
    _expect(sidecar.exists(), "sidecar .txt created")

    content = sidecar.read_text(encoding="utf-8")
    _expect("# pyCollect Case Notes" in content, "header present")
    _expect("# Case: roundtrip.drc" in content, "case name in header")
    _expect("Alpha note" in content, "first note persisted")
    _expect("Beta note" in content, "second note persisted")

    nm2 = CaseNotesManager({"enabled": True})
    loaded = nm2.load_for_review(drc)
    _expect(loaded, "load_for_review returns True")
    _expect(nm2.note_count() == 2, "two notes loaded from sidecar")
    _expect(nm2.get_note(0)["text"] == "Alpha note", "first note text matches")
    _expect(nm2.get_note(1)["text"] == "Beta note", "second note text matches")


def test_autosave():
    print("[3] Autosave")
    tmpdir = Path(tempfile.mkdtemp())
    drc = tmpdir / "autosave.drc"
    drc.write_bytes(b"fake")

    nm = CaseNotesManager({"enabled": True, "autosave_interval_sec": 5})
    nm.start_session(drc)
    nm.insert_note("Auto note")
    _expect(nm.is_dirty(), "dirty after insert")

    nm.autosave_if_needed()
    _expect(not nm.is_dirty(), "clean after autosave")
    _expect(drc.with_suffix(".txt").exists(), "sidecar written by autosave")


def test_disabled_config():
    print("[4] Disabled config")
    nm = CaseNotesManager({"enabled": False})
    _expect(not nm.enabled, "enabled=False respected")

    nm2 = CaseNotesManager({})
    _expect(nm2.enabled, "default enabled=True")
    _expect(nm2.templates == [], "empty templates by default")
    _expect(nm2.autosave_interval_sec == 30, "default autosave 30s")


def test_templates_from_config():
    print("[5] Templates from config")
    tpl = ["Drug administered", "Intubation start", "Artifact suspected"]
    nm = CaseNotesManager({"templates": tpl})
    _expect(nm.templates == tpl, "templates match config")
    _expect(nm.templates is not tpl, "templates are a copy")


def test_clear_and_multi_delete():
    print("[6] Clear and multi-delete")
    nm = CaseNotesManager({"enabled": True})
    nm.start_session(Path(tempfile.mkdtemp()) / "test.drc")
    for i in range(5):
        nm.insert_note(f"Note {i}")
    _expect(nm.note_count() == 5, "five notes")

    nm.delete_notes([1, 3])
    _expect(nm.note_count() == 3, "three after multi-delete")
    remaining = [nm.get_note(i)["text"] for i in range(3)]
    _expect(remaining == ["Note 0", "Note 2", "Note 4"], "correct notes remain")

    nm.clear()
    _expect(nm.note_count() == 0, "zero after clear")


def test_load_missing_sidecar():
    print("[7] Load missing sidecar")
    tmpdir = Path(tempfile.mkdtemp())
    drc = tmpdir / "no_notes.drc"
    drc.write_bytes(b"fake")

    nm = CaseNotesManager({"enabled": True})
    loaded = nm.load_for_review(drc)
    _expect(not loaded, "load_for_review returns False when no sidecar")
    _expect(nm.note_count() == 0, "zero notes when sidecar missing")


# ── GUI integration tests ────────────────────────────────────────────

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


def test_gui_notes_section(win: gui.PyCollectQtWindow):
    print("[8] GUI notes section exists")
    _expect(hasattr(win, "notes_section"), "notes_section attribute exists")
    _expect(hasattr(win, "notes_table"), "notes_table attribute exists")
    _expect(hasattr(win, "notes_manager"), "notes_manager attribute exists")
    _expect(isinstance(win.notes_manager, CaseNotesManager),
            "notes_manager is CaseNotesManager instance")


def test_gui_notes_buttons(win: gui.PyCollectQtWindow):
    print("[9] GUI notes buttons exist")
    _expect(hasattr(win, "notes_insert_btn"), "insert button exists")
    _expect(hasattr(win, "notes_template_btn"), "template button exists")
    _expect(hasattr(win, "notes_delete_btn"), "delete button exists")
    _expect(hasattr(win, "notes_clear_btn"), "clear button exists")


def test_gui_notes_table_empty(win: gui.PyCollectQtWindow):
    print("[10] GUI notes table starts empty")
    _expect(win.notes_table.rowCount() == 0, "table has 0 rows initially")
    _expect(win.notes_table.columnCount() == 2, "table has 2 columns (Time, Note)")


def test_gui_notes_template_menu(win: gui.PyCollectQtWindow):
    print("[11] GUI template menu populated")
    menu = getattr(win, "_notes_template_menu", None)
    _expect(menu is not None, "template menu exists")
    if menu is not None:
        actions = menu.actions()
        _expect(len(actions) > 0, f"template menu has {len(actions)} actions")


def test_gui_notes_nav_buttons(win: gui.PyCollectQtWindow):
    print("[12] GUI review nav buttons")
    _expect(hasattr(win, "prev_note_btn"), "prev_note_btn exists")
    _expect(hasattr(win, "next_note_btn"), "next_note_btn exists")


def test_gui_notes_autosave_timer(win: gui.PyCollectQtWindow):
    print("[13] GUI autosave timer")
    _expect(hasattr(win, "_notes_autosave_timer"), "autosave timer exists")
    _expect(win._notes_autosave_timer.interval() > 0, "autosave timer has positive interval")


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # Pure CaseNotesManager tests (no GUI)
    test_insert_edit_delete()
    test_save_load_roundtrip()
    test_autosave()
    test_disabled_config()
    test_templates_from_config()
    test_clear_and_multi_delete()
    test_load_missing_sidecar()

    # GUI integration tests
    win = _make_window()
    test_gui_notes_section(win)
    test_gui_notes_buttons(win)
    test_gui_notes_table_empty(win)
    test_gui_notes_template_menu(win)
    test_gui_notes_nav_buttons(win)
    test_gui_notes_autosave_timer(win)
    win.close()
    QtWidgets.QApplication.processEvents()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} failure(s)")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
