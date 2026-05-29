"""Case notes manager for pyCollect GUI (PS_COLLECT_UI_009 / PS_COLLECT_UI_010).

Manages in-memory note entries, autosave to .txt sidecar, and review load.
"""
from datetime import datetime, timezone
from pathlib import Path


class CaseNotesManager:
    """Manages case notes for a pyCollect recording session.

    Notes are stored in a plain UTF-8 .txt sidecar alongside the .drc file.
    Each note row has:
        display_time  : ISO 8601 local timestamp shown in the table
        monitor_time_utc : UTC unix timestamp from monitor, or "" if unavailable
        pc_time_utc   : PC wall-clock UTC at insertion (always populated)
        time_source   : "monitor" or "pc"
        text          : free-text note content

    File format::
        # pyCollect Case Notes
        # Case: record_20260529_170235.drc
        2026-05-29 17:06:13 | SpO2 low
        2026-05-29 17:07:10 | Drug administered
    """

    FILE_HEADER = "# pyCollect Case Notes\n"

    def __init__(self, notes_config: dict):
        self._config = notes_config or {}
        self._notes: list[dict] = []      # each: {display_time, text, ...}
        self._drc_path: Path | None = None
        self._dirty = False

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled", True))

    @property
    def templates(self) -> list[str]:
        return list(self._config.get("templates", []))

    @property
    def autosave_interval_sec(self) -> int:
        return int(self._config.get("autosave_interval_sec", 30))

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self, drc_path: str | Path):
        """Call when a new DRC file is opened for writing."""
        self._drc_path = Path(drc_path)
        self._notes = []
        self._dirty = False

    def end_session(self):
        """Call when capture stops; flushes the sidecar file."""
        if self._notes and self._drc_path:
            self._write_sidecar()
        self._drc_path = None
        self._dirty = False

    def clear(self):
        """Remove all notes from memory (does not delete sidecar)."""
        self._notes = []
        self._dirty = True

    # ------------------------------------------------------------------
    # Note insertion
    # ------------------------------------------------------------------

    def insert_note(
        self,
        text: str,
        monitor_time_unix: int | None = None,
    ) -> dict:
        """Insert a new timestamped note and return the note dict.

        Parameters
        ----------
        text:
            The note text.
        monitor_time_unix:
            Unix timestamp from the monitor (if available, used as primary
            display time).  If None, PC clock is used.
        """
        pc_now = datetime.now()
        pc_now_utc = datetime.now(tz=timezone.utc)

        if monitor_time_unix is not None:
            try:
                monitor_dt_local = datetime.fromtimestamp(float(monitor_time_unix))
                display_time = monitor_dt_local.strftime("%Y-%m-%d %H:%M:%S")
                time_source = "monitor"
                monitor_time_str = str(int(monitor_time_unix))
            except Exception:
                display_time = pc_now.strftime("%Y-%m-%d %H:%M:%S")
                time_source = "pc"
                monitor_time_str = ""
        else:
            display_time = pc_now.strftime("%Y-%m-%d %H:%M:%S")
            time_source = "pc"
            monitor_time_str = ""

        note = {
            "display_time": display_time,
            "monitor_time_utc": monitor_time_str,
            "pc_time_utc": pc_now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "time_source": time_source,
            "text": str(text or "").strip(),
        }
        self._notes.append(note)
        self._dirty = True
        return note

    def update_note_text(self, index: int, text: str):
        """Update the text of an existing note (called from table edit)."""
        if 0 <= index < len(self._notes):
            self._notes[index]["text"] = str(text or "").strip()
            self._dirty = True

    def update_note_time(self, index: int, display_time: str):
        """Update the display time string of an existing note."""
        if 0 <= index < len(self._notes):
            self._notes[index]["display_time"] = str(display_time or "").strip()
            self._dirty = True

    def delete_note(self, index: int):
        """Remove a note by index."""
        if 0 <= index < len(self._notes):
            self._notes.pop(index)
            self._dirty = True

    def delete_notes(self, indices: list[int]):
        """Remove multiple notes by indices (removes in reverse order)."""
        for idx in sorted(set(indices), reverse=True):
            if 0 <= idx < len(self._notes):
                self._notes.pop(idx)
        self._dirty = True

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def note_count(self) -> int:
        return len(self._notes)

    def get_note(self, index: int) -> dict | None:
        if 0 <= index < len(self._notes):
            return dict(self._notes[index])
        return None

    def all_notes(self) -> list[dict]:
        return [dict(n) for n in self._notes]

    def is_dirty(self) -> bool:
        return self._dirty

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def autosave_if_needed(self):
        """Write sidecar if dirty and a DRC path is set."""
        if self._dirty and self._drc_path and self._notes:
            self._write_sidecar()

    def _sidecar_path(self) -> Path | None:
        if self._drc_path is None:
            return None
        return self._drc_path.with_suffix(".txt")

    def _write_sidecar(self):
        path = self._sidecar_path()
        if path is None:
            return
        try:
            lines = [
                self.FILE_HEADER.rstrip("\n"),
                f"# Case: {self._drc_path.name}",
                "",
            ]
            for note in self._notes:
                text = str(note.get("text", "")).replace("\n", " ")
                lines.append(f"{note['display_time']} | {text}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._dirty = False
        except Exception:
            pass

    def load_for_review(self, drc_path: str | Path) -> bool:
        """Load the sidecar .txt for a DRC file opened in review mode.

        Returns True if a sidecar was found and loaded, False otherwise.
        """
        drc = Path(drc_path)
        txt = drc.with_suffix(".txt")
        if not txt.exists():
            self._notes = []
            self._drc_path = drc
            self._dirty = False
            return False

        try:
            lines = txt.read_text(encoding="utf-8").splitlines()
        except Exception:
            self._notes = []
            self._drc_path = drc
            self._dirty = False
            return False

        notes = []
        for line in lines:
            if line.startswith("#") or not line.strip():
                continue
            if " | " in line:
                ts, _, text = line.partition(" | ")
                notes.append({
                    "display_time": ts.strip(),
                    "monitor_time_utc": "",
                    "pc_time_utc": "",
                    "time_source": "file",
                    "text": text.strip(),
                })
            else:
                notes.append({
                    "display_time": "",
                    "monitor_time_utc": "",
                    "pc_time_utc": "",
                    "time_source": "file",
                    "text": line.strip(),
                })

        self._notes = notes
        self._drc_path = drc
        self._dirty = False
        return True

    # ------------------------------------------------------------------
    # Review navigation helpers
    # ------------------------------------------------------------------

    def find_prev_note_index(self, current_review_record_index: int, record_timestamps: list) -> int | None:
        """Find the review record index for the note before current position.

        Parameters
        ----------
        current_review_record_index:
            Current slider position.
        record_timestamps:
            List of float start_time values from review_records.

        Returns the review record index to jump to, or None if none found.
        """
        if not self._notes or not record_timestamps:
            return None
        current_t = float(record_timestamps[current_review_record_index])
        best_rec_idx = None
        best_t = None
        for note in self._notes:
            note_t = self._parse_display_time_to_offset(note["display_time"], record_timestamps)
            if note_t is None:
                continue
            if note_t < current_t:
                if best_t is None or note_t > best_t:
                    best_t = note_t
                    best_rec_idx = self._time_to_record_index(note_t, record_timestamps)
        return best_rec_idx

    def find_next_note_index(self, current_review_record_index: int, record_timestamps: list) -> int | None:
        """Find the review record index for the note after current position."""
        if not self._notes or not record_timestamps:
            return None
        current_t = float(record_timestamps[current_review_record_index])
        best_rec_idx = None
        best_t = None
        for note in self._notes:
            note_t = self._parse_display_time_to_offset(note["display_time"], record_timestamps)
            if note_t is None:
                continue
            if note_t > current_t:
                if best_t is None or note_t < best_t:
                    best_t = note_t
                    best_rec_idx = self._time_to_record_index(note_t, record_timestamps)
        return best_rec_idx

    @staticmethod
    def _parse_display_time_to_offset(display_time: str, record_timestamps: list) -> float | None:
        """Not fully implemented: returns first record offset as placeholder."""
        if not display_time:
            return None
        # Future: cross-reference display_time with header UTC timestamps
        return None

    @staticmethod
    def _time_to_record_index(t: float, record_timestamps: list) -> int:
        """Return the record index whose start_time is closest to t."""
        best = 0
        best_diff = abs(float(record_timestamps[0]) - t)
        for i, ts in enumerate(record_timestamps):
            diff = abs(float(ts) - t)
            if diff < best_diff:
                best_diff = diff
                best = i
        return best
