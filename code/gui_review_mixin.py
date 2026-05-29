"""Review, CSV conversion, and file-state mixin for PyCollectQtWindow."""
import json
import math
import re
import struct
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from PyQt5 import QtCore, QtWidgets

from collector_worker import CollectorWorker
from csv_conversion_worker import CsvConversionWorker


class _GuiReviewMixin:
    """Review file loading, CSV conversion, and file-status helpers."""

    # ── File save status ──────────────────────────────────────────────

    def _set_file_save_status(self, state, file_path=""):
        self.current_file_state = state
        self.current_output_file = str(file_path or "").strip()
        text = "No active DRC file"
        if self.current_output_file:
            text = Path(self.current_output_file).name

        bg, fg = self._save_state_colors(state)
        self.save_file_name_label.setText(self._wrap_sidebar_text(text, width=34))
        self.save_file_name_label.setToolTip(self.current_output_file)
        self.save_file_name_label.setStyleSheet(
            "padding:6px;border-radius:4px;"
            f"background:{bg};color:{fg};font-weight:600;"
        )

        active_input = self._active_drc_input_path()
        can_convert = (
            bool(active_input)
            and Path(active_input).exists()
            and not self.csv_convert_in_progress
        )
        self.convert_csv_btn.setVisible(
            can_convert or self.csv_convert_in_progress
        )
        self.convert_csv_btn.setEnabled(can_convert)
        if not self.csv_convert_in_progress:
            self._set_convert_button_progress(None)
        self._refresh_review_button_state()
        self._refresh_log_file_label()

    def _refresh_review_button_state(self):
        active_input = self._active_drc_input_path()
        can_review = (
            bool(active_input)
            and Path(active_input).exists()
            and not self._is_capture_running()
        )
        self.review_btn.setEnabled(can_review)

    def _refresh_log_file_label(self):
        if not hasattr(self, "log_file_label"):
            return
        active_input = self._active_drc_input_path()
        if active_input:
            log_path = Path(active_input).with_suffix(".log")
            if log_path.exists():
                self.log_file_header.setVisible(True)
                self.log_file_label.setVisible(True)
                summary = self._parse_capture_log_summary(log_path)
                self.log_file_label.setText(summary)
                self.log_file_label.setToolTip(str(log_path))
                return
        self.log_file_header.setVisible(False)
        self.log_file_label.setVisible(False)

    def _parse_capture_log_summary(self, log_path):
        try:
            text = log_path.read_text(encoding="utf-8")
        except Exception:
            return log_path.name

        pc_start_m = re.search(r"pc_start=([0-9\-: ]+)", text)
        pc_end_m = re.search(r"pc_end=([0-9\-: ]+)", text)
        mon_first_m = re.search(r"monitor_first_record=(\d+)\s*\(([^)]+)\)", text)
        mon_last_m = re.search(r"monitor_last_record=(\d+)\s*\(([^)]+)\)", text)
        trends_m = re.search(r"trend_record_count=(\d+)", text)
        waves_m = re.search(r"waveform_record_count=(\d+)", text)
        alarms_m = re.search(r"alarm_record_count=(\d+)", text)

        lines = []
        if pc_start_m and pc_end_m:
            try:
                t0 = datetime.strptime(pc_start_m.group(1).strip(), "%Y-%m-%d %H:%M:%S")
                t1 = datetime.strptime(pc_end_m.group(1).strip(), "%Y-%m-%d %H:%M:%S")
                dur = int((t1 - t0).total_seconds())
                lines.append(f"Duration: {dur}s")
            except Exception:
                pass
        if pc_start_m and mon_first_m:
            try:
                pc_t = datetime.strptime(pc_start_m.group(1).strip(), "%Y-%m-%d %H:%M:%S")
                mon_utc = datetime.strptime(mon_first_m.group(2).strip(), "%Y-%m-%d %H:%M:%S UTC")
                lines.append(f"PC\u2013Monitor offset (start): {int((pc_t - mon_utc).total_seconds()):+d}s")
            except Exception:
                pass
        if pc_end_m and mon_last_m:
            try:
                pc_t = datetime.strptime(pc_end_m.group(1).strip(), "%Y-%m-%d %H:%M:%S")
                mon_utc = datetime.strptime(mon_last_m.group(2).strip(), "%Y-%m-%d %H:%M:%S UTC")
                lines.append(f"PC\u2013Monitor offset (end): {int((pc_t - mon_utc).total_seconds()):+d}s")
            except Exception:
                pass
        counts = []
        if trends_m:
            counts.append(f"T:{trends_m.group(1)}")
        if waves_m:
            counts.append(f"W:{waves_m.group(1)}")
        if alarms_m:
            counts.append(f"A:{alarms_m.group(1)}")
        if counts:
            lines.append("Records: " + " ".join(counts))
        return "\n".join(lines) if lines else log_path.name

    def _set_convert_button_progress(self, percent):
        if percent is None:
            self.convert_csv_btn.setText("Convert Current DRC to CSV")
            self.convert_csv_btn.setStyleSheet("")
            return
        pct = max(0, min(100, int(percent)))
        split = pct / 100.0
        done_bg = self._cfg_color("buttons", "active_bg", "#00d4ff")
        rest_bg = self._cfg_color("buttons", "normal_bg", "#1a3a52")
        txt = self._cfg_color("buttons", "normal_text", "#e8e8e8")
        self.convert_csv_btn.setText(f"Converting... {pct}%")
        self.convert_csv_btn.setStyleSheet(
            "QPushButton {"
            "font-weight: 600;"
            f"color: {txt};"
            "border-radius: 3px;"
            "padding: 4px;"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {done_bg},"
            f"stop:{split:.4f} {done_bg},"
            f"stop:{split:.4f} {rest_bg},"
            f"stop:1 {rest_bg});"
            "}"
        )

    def _show_saved_csv_paths(self, saved_paths):
        self.convert_saved_list.clear()
        if not saved_paths:
            self.convert_saved_header.setVisible(False)
            self.convert_saved_list.setVisible(False)
            return
        for path_text in saved_paths:
            item = QtWidgets.QListWidgetItem(str(path_text))
            item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            item.setToolTip(str(path_text))
            self.convert_saved_list.addItem(item)
        self.convert_saved_header.setVisible(True)
        self.convert_saved_list.setVisible(True)

    # ── Review state management ───────────────────────────────────────

    def _clear_review_state(self):
        self.review_mode = False
        self.review_file_path = ""
        self.review_records = []
        self.review_record_index = 0
        self.review_trend_history_by_row = {}
        self.review_wave_history_by_id = {}
        self.review_first_header_utc = None
        self.review_last_header_utc = None
        self.review_row_widget.setVisible(False)
        self.review_slider.blockSignals(True)
        self.review_slider.setMinimum(0)
        self.review_slider.setMaximum(0)
        self.review_slider.setValue(0)
        self.review_slider.blockSignals(False)
        self.review_slider_value_label.setText("--")
        self.review_dri_level_label.setVisible(False)
        self._notes_reload_table()
        self._update_notes_nav_buttons_visibility(False)

    def _clear_runtime_buffers(self):
        import time
        self.logical_now_sec = 0.0
        self.first_record_header_utc = None
        self.last_record_header_utc = None
        self.wave_last_seen_monotonic.clear()
        self.wave_last_seen_by_row.clear()
        self.wave_user_unrequested_rows.clear()
        self.capture_started_monotonic = time.monotonic()
        self.last_alarm_text = "none"
        self.last_alarm_color = None
        self.last_alarm_seen_monotonic = None
        self._last_trend_unix = None
        self.dri_level_label.setVisible(False)
        self.trend_history_by_row.clear()
        self.review_btn.setEnabled(False)
        for values in self.trend_buffers.values():
            values.clear()
        for values in self.wave_buffers.values():
            values.clear()
        for key in self.wave_cursors:
            self.wave_cursors[key] = None

    def _build_review_parser(self):
        review_wave_defs = []
        for item in self.all_wave_defs:
            cloned = dict(item)
            cloned["id"] = f"w_{int(item['row_identifier'])}"
            review_wave_defs.append(cloned)
        return CollectorWorker(
            port="",
            duration_sec=0,
            all_trend_defs=self.all_trend_defs,
            all_wave_defs=self.all_wave_defs,
            trend_defs=self.trend_defs,
            wave_defs=review_wave_defs,
            baudrate=int(self.baud_combo.currentText() or "19200"),
            output_name=self.output_name,
            simulation_mode=True,
            no_rtscts=True,
        )

    def _load_review_dataset(self, file_path):
        parser = self._build_review_parser()
        trend_history = {}
        wave_history = {
            f"w_{int(item['row_identifier'])}": []
            for item in self.all_wave_defs
        }
        wave_cursors = {key: None for key in wave_history.keys()}
        wave_meta_by_id = {
            f"w_{int(item['row_identifier'])}": item
            for item in self.all_wave_defs
        }
        records = []
        first_header_utc = None
        last_header_utc = None
        first_record_time_unix = None
        last_alarm_text = "none"
        last_alarm_color = None
        review_dri_level = None

        with Path(file_path).open("rb") as fp:
            rec_idx = 0
            while True:
                header = fp.read(40)
                if len(header) < 40:
                    break
                r_len = struct.unpack_from("<h", header, 0)[0]
                if r_len < 40:
                    break
                body = fp.read(r_len - 40)
                if len(body) < (r_len - 40):
                    break
                rec_idx += 1
                record_data = header + body
                payload = parser._extract_from_record(record_data)
                if review_dri_level is None:
                    dri = payload.get("dri_level")
                    if dri is not None and dri > 0:
                        review_dri_level = dri
                rel_t = float(rec_idx - 1)

                header_dt = None
                record_time_unix = payload.get("record_time_unix")
                if record_time_unix is not None:
                    if first_record_time_unix is None:
                        first_record_time_unix = float(record_time_unix)
                    rel_t = max(
                        0.0,
                        float(record_time_unix) - float(first_record_time_unix),
                    )
                    try:
                        header_dt = datetime.fromtimestamp(
                            float(record_time_unix), tz=timezone.utc
                        )
                    except Exception:
                        header_dt = None
                if header_dt is not None:
                    if first_header_utc is None:
                        first_header_utc = header_dt
                    last_header_utc = header_dt

                trends_invalid = set(payload.get("trends_invalid", []))
                trend_rows = payload.get("trend_rows", {}) or {}
                for row_key, value in trend_rows.items():
                    if value is None or math.isnan(value):
                        continue
                    row_id = int(row_key)
                    history = trend_history.setdefault(row_id, [])
                    history.append((rel_t, float(value), f"t_{row_id}" in trends_invalid))

                waves = payload.get("waves", {}) or {}
                waves_invalid = payload.get("waves_invalid", {}) or {}
                for chan_id, samples in waves.items():
                    if not samples:
                        continue
                    meta = wave_meta_by_id.get(chan_id)
                    if meta is None:
                        continue
                    sample_period = 1.0 / max(1.0, float(meta["sample_hz"]))
                    if wave_cursors[chan_id] is None:
                        wave_cursors[chan_id] = rel_t
                    else:
                        wave_cursors[chan_id] = max(float(wave_cursors[chan_id]), rel_t)
                    invalid_flags = waves_invalid.get(chan_id, [])
                    for idx, sample in enumerate(samples):
                        t_val = wave_cursors[chan_id]
                        wave_cursors[chan_id] += sample_period
                        wave_history[chan_id].append(
                            (t_val, float(sample), bool(invalid_flags[idx]) if idx < len(invalid_flags) else False)
                        )

                alarm_items = payload.get("alarms", []) or []
                if alarm_items:
                    alarm_texts = []
                    alarm_color_val = None
                    for item in alarm_items[:5]:
                        if isinstance(item, dict):
                            text = str(item.get("text", "")).strip()
                            color = item.get("color")
                        else:
                            text = str(item).strip()
                            color = None
                        if not text:
                            continue
                        alarm_texts.append(text)
                        if alarm_color_val is None and isinstance(color, int):
                            alarm_color_val = color
                    if alarm_texts:
                        last_alarm_text = " | ".join(alarm_texts[:5])
                        last_alarm_color = alarm_color_val

                records.append({
                    "start_time": rel_t,
                    "record_header_utc": header_dt,
                    "alarm_text": last_alarm_text,
                    "alarm_color": last_alarm_color,
                })

        if not records:
            raise RuntimeError("No DRC records found in review file")

        return {
            "records": records,
            "trend_history": trend_history,
            "wave_history": wave_history,
            "first_header_utc": first_header_utc,
            "last_header_utc": last_header_utc,
            "dri_level": review_dri_level,
        }

    @staticmethod
    def _build_review_series(points, start_sec, window_sec, gap_sec=1.0, hold_last=False):
        end_sec = start_sec + window_sec
        x_vals = []
        y_vals = []
        invalid_vals = []
        prev_t = None
        if hold_last:
            prev_point = None
            for point in points:
                if point[0] <= start_sec:
                    prev_point = point
                    continue
                break
            if prev_point is not None:
                x_vals.append(0.0)
                y_vals.append(prev_point[1])
                invalid_vals.append(bool(prev_point[2]))
                prev_t = start_sec
        for t_val, y_val, invalid_flag in points:
            if t_val < start_sec:
                continue
            if t_val > end_sec:
                break
            if not hold_last and prev_t is not None and (t_val - prev_t) > gap_sec:
                x_vals.append(float("nan"))
                y_vals.append(float("nan"))
                invalid_vals.append(False)
            x_vals.append(t_val - start_sec)
            y_vals.append(y_val)
            invalid_vals.append(bool(invalid_flag))
            prev_t = t_val
        return x_vals, y_vals, invalid_vals

    # ── Review UI event handlers ──────────────────────────────────────

    def _on_review_clicked(self):
        if self._is_capture_running():
            self.log("Stop monitoring before opening review")
            return
        review_input = str(self.review_source_file or "").strip()
        if not review_input:
            review_input = self._active_drc_input_path()
        if not review_input or not Path(review_input).exists():
            self.log("No DRC review file available")
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            dataset = self._load_review_dataset(review_input)
        except Exception as exc:
            self.log(f"ERROR: review load failed: {exc}")
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        self.review_mode = True
        self.review_file_path = review_input
        self.review_records = dataset["records"]
        self.review_trend_history_by_row = dataset["trend_history"]
        self.review_wave_history_by_id = dataset["wave_history"]
        self.review_first_header_utc = dataset["first_header_utc"]
        self.review_last_header_utc = dataset["last_header_utc"]

        dri = dataset.get("dri_level")
        if dri is not None and dri > 0:
            self.review_dri_level_label.setText(f"DRI Level: {dri}")
            self.review_dri_level_label.setVisible(True)
        else:
            self.review_dri_level_label.setVisible(False)

        self.review_row_widget.setVisible(True)
        self.review_slider.blockSignals(True)
        self.review_slider.setMinimum(0)
        self.review_slider.setMaximum(max(0, len(self.review_records) - 1))
        self.review_slider.setValue(0)
        self.review_slider.blockSignals(False)
        self.review_record_index = 0
        self.last_active_drc_file = str(self.review_file_path)
        self.log(f"Review opened: {Path(self.review_file_path).name}")
        self._refresh_log_file_label()
        self._update_graph_header()
        self.update_plots(force=True)
        self._update_mode_ui()

        # Load notes sidecar for this DRC
        loaded = self.notes_manager.load_for_review(review_input)
        self._notes_reload_table()
        self._update_notes_nav_buttons_visibility(loaded)

    def _on_review_slider_changed(self, value):
        if not self.review_mode or not self.review_records:
            return
        self.review_record_index = max(
            0, min(int(value), len(self.review_records) - 1)
        )
        self._update_graph_header()
        self.update_plots(force=True)

    def _on_exit_review_clicked(self):
        if not self.review_mode:
            return
        self._clear_review_state()
        self._update_graph_header()
        self.update_plots(force=True)
        self.update_plots()
        self.log("Review closed; returned to capture context")
        self._update_mode_ui()

    def _on_prev_note_clicked(self):
        if not self.review_mode or not self.review_records:
            return
        record_timestamps = [r.get("start_time", 0.0) for r in self.review_records]
        idx = self.notes_manager.find_prev_note_index(
            self.review_record_index, record_timestamps
        )
        if idx is not None:
            self.review_slider.setValue(idx)

    def _on_next_note_clicked(self):
        if not self.review_mode or not self.review_records:
            return
        record_timestamps = [r.get("start_time", 0.0) for r in self.review_records]
        idx = self.notes_manager.find_next_note_index(
            self.review_record_index, record_timestamps
        )
        if idx is not None:
            self.review_slider.setValue(idx)

    def _update_notes_nav_buttons_visibility(self, visible: bool):
        """Show/hide ◀Note / Note▶ buttons in the review slider row."""
        if hasattr(self, "prev_note_btn"):
            self.prev_note_btn.setVisible(visible)
        if hasattr(self, "next_note_btn"):
            self.next_note_btn.setVisible(visible)

    # ── Signal source paths ───────────────────────────────────────────

    def _signal_source_paths(self):
        config_path = Path(self.config.get("path", ""))
        base_dir = config_path.parent if config_path.exists() else Path.cwd()
        params_path = base_dir / "params5.txt"
        waves_path = base_dir / "waves5.txt"
        if config_path.exists():
            try:
                raw_cfg = json.loads(config_path.read_text(encoding="utf-8"))
                src = raw_cfg.get("signal_sources", {})
                params_rel = src.get("params_file")
                waves_rel = src.get("waves_file")
                if params_rel:
                    params_path = (base_dir / str(params_rel)).resolve()
                if waves_rel:
                    waves_path = (base_dir / str(waves_rel)).resolve()
            except Exception:
                pass
        return params_path, waves_path

    # ── CSV conversion ────────────────────────────────────────────────

    def convert_current_drc_to_csv(self):
        if self.csv_convert_in_progress:
            return
        active_input = self._active_drc_input_path()
        if not active_input:
            self.log("No DRC file available for conversion")
            return
        drc_path = Path(active_input)
        if not drc_path.exists():
            self.log(f"DRC file not found: {drc_path}")
            return
        params_path, waves_path = self._signal_source_paths()
        if not params_path.exists() or not waves_path.exists():
            self.log("Missing params/waves config files required for CSV conversion")
            return

        self.csv_convert_in_progress = True
        self.convert_csv_btn.setEnabled(False)
        self._set_convert_button_progress(0)
        self._show_saved_csv_paths([])
        self.log(f"Converting to CSV: {drc_path.name}")

        self.csv_worker = CsvConversionWorker(
            drc_path=drc_path,
            params_path=params_path,
            waves_path=waves_path,
            parent=self,
        )
        self.csv_worker.progress_signal.connect(self.on_csv_progress)
        self.csv_worker.finished_signal.connect(self.on_csv_finished)
        self.csv_worker.error_signal.connect(self.on_csv_error)
        self.csv_worker.start()

    def on_csv_progress(self, percent, processed, total):
        self._set_convert_button_progress(percent)
        if total > 0:
            self.convert_csv_btn.setToolTip(f"{processed}/{total} records")
        else:
            self.convert_csv_btn.setToolTip(f"{percent}%")

    def on_csv_finished(self, saved_paths):
        self.csv_convert_in_progress = False
        self._set_file_save_status(self.current_file_state, self.current_output_file)
        self._show_saved_csv_paths(saved_paths)
        self.log("CSV conversion complete: " + ", ".join(Path(p).name for p in saved_paths))
        self.csv_worker = None

    def on_csv_error(self, error_message):
        self.csv_convert_in_progress = False
        self._set_file_save_status(self.current_file_state, self.current_output_file)
        self._show_saved_csv_paths([])
        self.log(f"CSV conversion failed: {error_message}")
        self.csv_worker = None

    # ── Output path helpers ───────────────────────────────────────────

    def _default_output_directory(self):
        cfg_dir = Path(self.config.get("config_dir", "") or Path.cwd())
        return str((cfg_dir / "output").resolve())

    @staticmethod
    def _wrap_sidebar_text(text, width=42):
        value = str(text or "").strip()
        if not value:
            return ""
        return "\n".join(
            textwrap.wrap(
                value, width=max(16, int(width)),
                break_long_words=True, break_on_hyphens=False,
            )
        )

    def _normalized_output_filename(self, name):
        text = str(name or "").strip()
        if not text:
            text = "record.drc"
        import os
        root, ext = os.path.splitext(text)
        if not ext:
            text = text + ".drc"
        return Path(text).name

    def _init_output_target(self):
        raw = str(self.output_name or "").strip()
        cfg_dir = str(self.config.get("initial_output_directory", "") or "").strip()
        cfg_name = str(self.config.get("initial_output_filename", "") or "").strip()
        if raw:
            out_path = Path(raw)
            if not out_path.is_absolute():
                out_path = (Path.cwd() / out_path).resolve()
            self.output_directory = str(out_path.parent)
            self.output_filename = self._normalized_output_filename(out_path.name)
        else:
            self.output_directory = cfg_dir or self._default_output_directory()
            self.output_filename = self._normalized_output_filename(cfg_name)
        self.output_name = str(Path(self.output_directory) / self.output_filename)
        if not self.review_source_file:
            self.review_source_file = self.output_name

    def _active_drc_input_path(self):
        for candidate in [
            str(self.last_active_drc_file or "").strip(),
            str(self.review_source_file or "").strip(),
            str(self.current_output_file or "").strip(),
            str(self.output_name or "").strip(),
        ]:
            if candidate:
                return candidate
        return ""

    def _auto_open_last_review_if_available(self):
        if self._is_capture_running() or self.review_mode:
            return
        review_input = self._active_drc_input_path()
        if not review_input:
            return
        candidate = Path(review_input)
        if not candidate.exists() or candidate.suffix.lower() != ".drc":
            return
        self.review_file_edit.setText(str(candidate))
        self._on_review_source_edited()
        self.log(f"Auto-opening last active review file: {candidate.name}")
        self._on_review_clicked()

    def _sync_output_target_from_inputs(self):
        folder = str(self.save_folder_edit.text() or "").strip()
        if not folder:
            folder = self._default_output_directory()
        filename = self._normalized_output_filename(self.save_filename_edit.text())
        self.output_directory = folder
        self.output_filename = filename
        self.output_name = str(Path(folder) / filename)

    def _on_browse_output_folder(self):
        start_dir = str(self.save_folder_edit.text() or "").strip()
        if not start_dir:
            start_dir = self._default_output_directory()
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select output folder", start_dir
        )
        if selected:
            self.save_folder_edit.setText(selected)

    def _on_browse_output_filename(self):
        start_path = str(self.output_name or "").strip()
        if not start_path:
            start_path = str(Path(self._default_output_directory()) / "record.drc")
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select recording file", start_path,
            "DRC Files (*.drc);;All Files (*)"
        )
        if selected:
            selected_path = Path(selected)
            self.save_folder_edit.setText(str(selected_path.parent))
            self.save_filename_edit.setText(
                self._normalized_output_filename(selected_path.name)
            )
            self._on_output_target_edited()

    def _sync_review_source_from_input(self):
        self.review_source_file = str(self.review_file_edit.text() or "").strip()
        self.review_file_edit.setToolTip(self.review_source_file)

    def _on_review_source_edited(self):
        self._sync_review_source_from_input()
        self._save_runtime_config()
        self._refresh_review_button_state()

    def _on_browse_review_file(self):
        start_path = str(self.review_source_file or "").strip()
        if not start_path:
            start_path = str(self.output_name or "").strip()
        if not start_path:
            start_path = self._default_output_directory()
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open DRC file for review", start_path,
            "DRC Files (*.drc);;All Files (*)"
        )
        if selected:
            self.review_file_edit.setText(str(Path(selected).resolve()))
            self._on_review_source_edited()
            self._on_review_clicked()

    def _on_output_target_edited(self):
        self._sync_output_target_from_inputs()
        if not str(self.review_file_edit.text() or "").strip():
            self.review_file_edit.setText(self.output_name)
            self._sync_review_source_from_input()
        self._save_runtime_config()
        self._refresh_review_button_state()

    def _on_trend_interval_changed(self, value):
        if not self.config_path.exists():
            return
        try:
            cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
            cfg.setdefault("ui", {})["trend_interval_sec"] = value
            self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _all_lockable_sections(self):
        return [s for s in [
            getattr(self, "conn_section", None),
            getattr(self, "file_save_section", None),
            getattr(self, "wave_catalog_section", None),
            getattr(self, "view_section", None),
            getattr(self, "signal_section", None),
            getattr(self, "status_section", None),
        ] if s is not None]

    def _toggle_all_locks(self):
        sections = self._all_lockable_sections()
        any_locked = any(s.is_locked for s in sections)
        if any_locked:
            for s in sections:
                s.set_locked(False)
            self._lock_btn.setText("🔓  Lock collapsed sections")
        else:
            for s in sections:
                if not s.toggle_btn.isChecked():
                    s.set_locked(True)
            if any(s.is_locked for s in sections):
                self._lock_btn.setText("🔒  Unlock all sections")
        self._persist_lock_state()

    def _persist_lock_state(self):
        if not self.config_path.exists():
            return
        try:
            cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
            cfg.setdefault("ui", {})
            cfg["ui"]["locked_sections"] = [
                s.title for s in self._all_lockable_sections() if s.is_locked
            ]
            self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _restore_lock_state(self):
        try:
            if not self.config_path.exists():
                return
            cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
            locked_titles = cfg.get("ui", {}).get("locked_sections", [])
            for s in self._all_lockable_sections():
                if s.title in locked_titles:
                    s.set_locked(True)
        except Exception:
            pass
