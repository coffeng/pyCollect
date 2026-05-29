"""Plot update mixin for PyCollectQtWindow.

Contains on_package, _update_graph_header, _build_wrapped_series, update_plots,
on_finished, on_error, and wave_mapping.
"""
import math
import time
from datetime import datetime, timezone


class _GuiPlotMixin:
    """Handles live and review plot rendering, and incoming data packages."""

    def on_wave_mapping(self, wave_row_ids):
        """Wave graphs are driven by catalog buttons; mapping is informational only."""
        pass

    def on_package(self, payload):
        rel_t = float(payload.get("time", 0.0))
        pkg_idx = int(payload.get("index", 0) or 0)
        record_time_unix = payload.get("record_time_unix")

        dri_level = payload.get("dri_level")
        if dri_level is not None and dri_level > 0:
            self.dri_level_label.setText(f"DRI Level: {dri_level}")
            self.dri_level_label.setVisible(True)

        if record_time_unix is not None:
            try:
                record_dt = datetime.fromtimestamp(
                    float(record_time_unix), tz=timezone.utc
                )
                self.last_record_header_utc = record_dt
                if self.first_record_header_utc is None:
                    self.first_record_header_utc = record_dt
            except Exception:
                pass

        trend_rows = payload.get("trend_rows", {})
        # Client-side trend decimation: skip trend records that arrive
        # sooner than the requested interval (monitor may ignore the
        # interval byte and always send at 10 s).
        if trend_rows and record_time_unix is not None:
            interval = self.trend_interval_spin.value()
            if self._last_trend_unix is not None:
                if (float(record_time_unix) - self._last_trend_unix) < interval:
                    trend_rows = {}
            if trend_rows:
                self._last_trend_unix = float(record_time_unix)
        waves = payload.get("waves", {})
        trends_invalid = set(payload.get("trends_invalid", []))
        waves_invalid = payload.get("waves_invalid", {}) or {}
        positive_trend_rows = payload.get("positive_trend_rows", [])
        positive_wave_rows = payload.get("positive_wave_rows", [])
        present_wave_rows = payload.get("present_wave_rows", [])
        alarm_items = payload.get("alarms", []) or []

        alarm_texts = []
        alarm_color = None
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
            if alarm_color is None and isinstance(color, int):
                alarm_color = color

        trend_invalid_count = len(trends_invalid)
        wave_invalid_count = sum(
            sum(1 for f in flags if bool(f))
            for flags in waves_invalid.values()
        )

        now_for_log = time.monotonic()
        if trend_invalid_count > 0 or wave_invalid_count > 0:
            self.invalid_detected_total += 1
            self.invalid_trend_points_total += trend_invalid_count
            self.invalid_wave_points_total += wave_invalid_count
            if (now_for_log - self._last_invalid_log_monotonic) >= 1.0:
                self._last_invalid_log_monotonic = now_for_log
                self.log(
                    "Invalid samples detected: "
                    f"pkg={pkg_idx}, "
                    f"trend_slots={trend_invalid_count}, "
                    f"wave_points={wave_invalid_count}, "
                    "render=grey@0"
                )
        else:
            if self.invalid_detected_total == 0 and (
                now_for_log - self._last_no_invalid_log_monotonic
            ) >= 30.0:
                self._last_no_invalid_log_monotonic = now_for_log
                self.log(
                    "No invalid samples detected yet "
                    f"(pkg={pkg_idx}); grey invalid overlay will not appear."
                )

        prev_trend_count = len(self.positive_trend_rows)
        self.positive_trend_rows.update(positive_trend_rows)
        self.positive_wave_rows.update(positive_wave_rows)
        if len(self.positive_trend_rows) != prev_trend_count:
            self._refresh_trend_button_states()

        if self.simulation_mode:
            self.sim_idle_timer.stop()

        now_mono = time.monotonic()
        for row_id in present_wave_rows:
            self.wave_last_seen_by_row[int(row_id)] = now_mono

        displayed_rows = self._displayed_wave_row_ids()
        for row_id in positive_wave_rows:
            row_id = int(row_id)
            self.wave_last_received_at[row_id] = now_mono
            self.wave_last_seen_by_row[row_id] = now_mono
            for item in self.wave_defs:
                chan_id = item["id"]
                if chan_id in waves and waves[chan_id]:
                    r = int(item.get("row_identifier", 0))
                    if r > 0:
                        self.wave_last_seen_by_row[r] = now_mono
        for row_id in displayed_rows:
            row = int(row_id)
            if row in self.wave_user_unrequested_rows:
                continue
            self.wave_requested_rows.add(row)
        self._refresh_wave_request_button_states()

        trend_window, _wave_window = self._effective_windows()
        from collections import deque
        for row_key, val in trend_rows.items():
            if val is None or math.isnan(val):
                continue
            row_id = int(row_key)
            history = self.trend_history_by_row.get(row_id)
            if history is None:
                history = deque()
                self.trend_history_by_row[row_id] = history
            trend_slot_id = f"t_{row_id}"
            is_invalid = trend_slot_id in trends_invalid
            history.append((rel_t, float(val), is_invalid))

        cutoff = rel_t - trend_window
        for history in self.trend_history_by_row.values():
            while history and history[0][0] < cutoff:
                history.popleft()

        self._sync_all_trend_buffers()

        max_wave_t = rel_t
        for item in self.wave_defs:
            chan_id = item["id"]
            samples = waves.get(chan_id)
            if not samples:
                continue
            sample_invalid_flags = waves_invalid.get(chan_id, [])
            self.wave_last_seen_monotonic[chan_id] = now_mono
            sample_period = 1.0 / max(1.0, float(item["sample_hz"]))
            if self.wave_cursors[chan_id] is None:
                self.wave_cursors[chan_id] = rel_t
            for idx, sample in enumerate(samples):
                t_val = self.wave_cursors[chan_id]
                self.wave_cursors[chan_id] += sample_period
                invalid_flag = bool(sample_invalid_flags[idx]) if idx < len(sample_invalid_flags) else False
                self.wave_buffers[chan_id].append((t_val, sample, invalid_flag))
                max_wave_t = max(max_wave_t, t_val)

        self.logical_now_sec = max(self.logical_now_sec, rel_t, max_wave_t)

        if alarm_texts:
            self.last_alarm_text = " | ".join(alarm_texts[:5])
            self.last_alarm_color = alarm_color
            self.last_alarm_seen_monotonic = time.monotonic()
            if (
                self.last_alarm_text != self.last_logged_alarm_text
                or self.last_alarm_color != self.last_logged_alarm_color
            ):
                self.log(
                    f"Alarm banner text: {self.last_alarm_text} "
                    f"(al_disp_color={self.last_alarm_color})"
                )
                self.last_logged_alarm_text = self.last_alarm_text
                self.last_logged_alarm_color = self.last_alarm_color

        self._update_graph_header()
        self.update_plots()

    def _update_graph_header(self):
        if self.review_mode and self.review_records:
            info = self.review_records[self.review_record_index]
            record_dt = info.get("record_header_utc")
            if record_dt is None:
                self.last_record_label.setText(
                    f"Review start (record): {self.review_record_index + 1}"
                )
            else:
                self.last_record_label.setText(
                    "Review start (header UTC): "
                    f"{record_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                )

            start_sec = float(info.get("start_time", 0.0))
            hh, mm, ss = int(start_sec) // 3600, (int(start_sec) % 3600) // 60, int(start_sec) % 60
            self.elapsed_label.setText(
                f"Review offset: {hh:02d}:{mm:02d}:{ss:02d} "
                f"({self.review_record_index + 1}/{len(self.review_records)})"
            )

            _trend_window, wave_window = self._effective_windows()
            end_sec = start_sec + wave_window
            row_to_label = {
                int(item["row_identifier"]): item["label"]
                for item in self.all_wave_defs
            }
            recent_wave_labels = []
            for item in self.all_wave_defs:
                chan_id = f"w_{int(item['row_identifier'])}"
                points = self.review_wave_history_by_id.get(chan_id, [])
                for t_val, _sample, _invalid in points:
                    if t_val < start_sec:
                        continue
                    if t_val > end_sec:
                        break
                    label = row_to_label.get(int(item["row_identifier"]), "")
                    if label:
                        recent_wave_labels.append(label)
                    break
            waves_text = ", ".join(recent_wave_labels) if recent_wave_labels else "none"
            self.recent_waves_label.setText(f"Waveforms (review window): {waves_text}")

            alarm_text = str(info.get("alarm_text") or "none")
            alarm_css = self._alarm_color_css(info.get("alarm_color"))
            if alarm_text == "none":
                alarm_css = self._cfg_color("text", "secondary", "#9aa0a6")
            self.recent_alarm_label.setText(f"Alarm: {alarm_text}")
            self.recent_alarm_label.setStyleSheet(f"font-weight: 600; color:{alarm_css};")

            last_info = self.review_records[-1]
            total_sec = float(last_info.get("start_time", 0.0))
            th, tm, ts = int(total_sec) // 3600, (int(total_sec) % 3600) // 60, int(total_sec) % 60
            slider_text = (
                f"{self.review_record_index + 1}/{len(self.review_records)}"
                f"  ({th:02d}:{tm:02d}:{ts:02d})"
            )
            self.review_slider_value_label.setText(slider_text)
            return

        if self.last_record_header_utc is None:
            self.last_record_label.setText("Last record (header UTC): --")
        else:
            self.last_record_label.setText(
                "Last record (header UTC): "
                f"{self.last_record_header_utc.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        if self.first_record_header_utc is None or self.last_record_header_utc is None:
            self.elapsed_label.setText("Elapsed (header): --")
        else:
            elapsed_sec = max(0, int(
                (self.last_record_header_utc - self.first_record_header_utc).total_seconds()
            ))
            hh, mm, ss = elapsed_sec // 3600, (elapsed_sec % 3600) // 60, elapsed_sec % 60
            self.elapsed_label.setText(f"Elapsed (header): {hh:02d}:{mm:02d}:{ss:02d}")

        now_mono = time.monotonic()
        recent_wave_labels = []
        row_to_label = {
            int(item["row_identifier"]): item["label"]
            for item in self.all_wave_defs
        }
        if self.simulation_mode:
            for row_id in sorted(self.wave_last_seen_by_row.keys()):
                last_seen = self.wave_last_seen_by_row.get(row_id)
                if last_seen is not None and (now_mono - float(last_seen)) <= self.WAVE_REQUEST_TIMEOUT_SEC:
                    label = row_to_label.get(row_id)
                    if label:
                        recent_wave_labels.append(label)
        else:
            for row_id in sorted(self.wave_last_seen_by_row.keys()):
                last_seen = self.wave_last_seen_by_row.get(row_id)
                if last_seen is not None and (now_mono - last_seen) <= 5.0:
                    label = row_to_label.get(row_id)
                    if label:
                        recent_wave_labels.append(label)

        text = ", ".join(recent_wave_labels) if recent_wave_labels else "none"
        if self.simulation_mode:
            header_text = f"Waveforms (available): {text}"
            self.recent_waves_label.setText(header_text)
            if self.debug_stdout and text != self._last_logged_available_waves:
                self.log(header_text)
                self._last_logged_available_waves = text
        else:
            self.recent_waves_label.setText(f"Waveforms (last 5s): {text}")

        alarm_text = "none"
        alarm_css = self._cfg_color("text", "secondary", "#9aa0a6")
        if self.last_alarm_seen_monotonic is not None:
            alarm_age = time.monotonic() - float(self.last_alarm_seen_monotonic)
            if alarm_age <= 30.0 and self.last_alarm_text:
                alarm_text = self.last_alarm_text
                alarm_css = self._alarm_color_css(self.last_alarm_color)
        self.recent_alarm_label.setText(f"Alarm: {alarm_text}")
        self.recent_alarm_label.setStyleSheet(f"font-weight: 600; color:{alarm_css};")

    @staticmethod
    def _build_wrapped_series(points, window_sec, now_sec, gap_sec=1.0):
        if not points:
            return [], [], []
        safe_window = max(0.1, float(window_sec))
        safe_gap = min(max(0.0, float(gap_sec)), max(0.0, safe_window - 0.1))
        x_vals, y_vals, invalid_vals = [], [], []
        prev_x = None
        for point in points:
            t_val, y_val = point[0], point[1]
            invalid_flag = bool(point[2]) if len(point) >= 3 else False
            age = now_sec - t_val
            if age < 0.0 or age > (safe_window - safe_gap):
                continue
            x_mod = t_val % safe_window
            if prev_x is not None and x_mod < prev_x:
                x_vals.append(float("nan"))
                y_vals.append(float("nan"))
                invalid_vals.append(False)
            x_vals.append(x_mod)
            y_vals.append(y_val)
            invalid_vals.append(invalid_flag)
            prev_x = x_mod
        return x_vals, y_vals, invalid_vals

    def update_plots(self, force=False):
        trend_gap_sec = 1.0
        try:
            trend_interval_sec = float(self.trend_interval_spin.value())
            trend_gap_sec = max(1.0, trend_interval_sec * 1.5)
        except Exception:
            pass

        if self.review_mode and self.review_records:
            self._update_plots_review(trend_gap_sec)
            return

        trend_window, wave_window = self._effective_windows()
        now_rel = float(self.logical_now_sec)

        def series_now(points):
            return float(points[-1][0]) if points else now_rel

        if force:
            for item in self.trend_defs:
                if item["id"] not in self.trend_curves:
                    continue
                self.trend_curves[item["id"]].setData([], [])
                self.trend_invalid_curves[item["id"]].setData([], [])
                self.trend_plots[item["id"]].setTitle(item["title"])
                self.trend_plots[item["id"]].setXRange(0, trend_window, padding=0.0)
            for item in self.wave_defs:
                if item["id"] not in self.wave_curves:
                    continue
                self.wave_curves[item["id"]].setData([], [])
                self.wave_invalid_curves[item["id"]].setData([], [])
                self.wave_plots[item["id"]].setTitle(item["title"])
                self.wave_plots[item["id"]].setXRange(0, wave_window, padding=0.0)
            return

        for item in self.trend_defs:
            if item["id"] not in self.trend_curves:
                continue
            points = self.trend_buffers.get(item["id"])
            if points:
                this_now = series_now(points)
                x_data, y_data, invalid_data = self._build_wrapped_series(
                    points, trend_window, this_now, gap_sec=trend_gap_sec
                )
                y_valid, y_invalid = self._split_valid_invalid(y_data, invalid_data)
                self.trend_curves[item["id"]].setData(x_data, y_valid)
                self.trend_invalid_curves[item["id"]].setData(x_data, y_invalid)
                latest = points[-1][1]
                latest_invalid = bool(points[-1][2]) if len(points[-1]) >= 3 else False
                if latest_invalid:
                    self.trend_plots[item["id"]].setTitle(f"{item['title']} : DATA_INVALID")
                else:
                    fmt = f"{latest:.0f}" if latest == round(latest) else f"{latest:.1f}"
                    self.trend_plots[item["id"]].setTitle(f"{item['title']} : {fmt}")
            self.trend_plots[item["id"]].setXRange(0, trend_window, padding=0.0)

        for item in self.wave_defs:
            if item["id"] not in self.wave_curves:
                continue
            points = self.wave_buffers.get(item["id"])
            if points:
                this_now = series_now(points)
                x_data, y_data, invalid_data = self._build_wrapped_series(
                    points, wave_window, this_now, gap_sec=1.0
                )
                y_valid, y_invalid = self._split_valid_invalid(y_data, invalid_data)
                self.wave_curves[item["id"]].setData(x_data, y_valid)
                self.wave_invalid_curves[item["id"]].setData(x_data, y_invalid)
                latest_invalid = bool(points[-1][2]) if len(points[-1]) >= 3 else False
                if latest_invalid:
                    self.wave_plots[item["id"]].setTitle(f"{item['title']} : DATA_INVALID")
                else:
                    self.wave_plots[item["id"]].setTitle(item["title"])
            self.wave_plots[item["id"]].setXRange(0, wave_window, padding=0.0)

    def _update_plots_review(self, trend_gap_sec):
        trend_window, wave_window = self._effective_windows()
        start_sec = float(
            self.review_records[self.review_record_index].get("start_time", 0.0)
        )
        for item in self.trend_defs:
            if item["id"] not in self.trend_curves:
                continue
            row_id = int(item["row_identifier"])
            points = self.review_trend_history_by_row.get(row_id, [])
            x_data, y_data, invalid_data = self._build_review_series(
                points, start_sec, trend_window, gap_sec=trend_gap_sec, hold_last=True
            )
            y_valid, y_invalid = [], []
            latest = None
            latest_invalid = False
            for value, inv in zip(y_data, invalid_data):
                if isinstance(value, float) and math.isnan(value):
                    y_valid.append(value)
                    y_invalid.append(value)
                    continue
                latest = value
                latest_invalid = bool(inv)
                if inv:
                    y_valid.append(float("nan"))
                    y_invalid.append(0.0)
                else:
                    y_valid.append(value)
                    y_invalid.append(float("nan"))
            self.trend_curves[item["id"]].setData(x_data, y_valid)
            self.trend_invalid_curves[item["id"]].setData(x_data, y_invalid)
            if latest is None:
                self.trend_plots[item["id"]].setTitle(item["title"])
            elif latest_invalid:
                self.trend_plots[item["id"]].setTitle(f"{item['title']} : DATA_INVALID")
            else:
                fmt = f"{latest:.0f}" if latest == round(latest) else f"{latest:.1f}"
                self.trend_plots[item["id"]].setTitle(f"{item['title']} : {fmt}")
            self.trend_plots[item["id"]].setXRange(0, trend_window, padding=0.0)

        for item in self.wave_defs:
            if item["id"] not in self.wave_curves:
                continue
            points = self.review_wave_history_by_id.get(item["id"], [])
            x_data, y_data, invalid_data = self._build_review_series(
                points, start_sec, wave_window, gap_sec=1.0
            )
            y_valid, y_invalid = [], []
            latest_invalid = False
            has_wave = False
            for value, inv in zip(y_data, invalid_data):
                if isinstance(value, float) and math.isnan(value):
                    y_valid.append(value)
                    y_invalid.append(value)
                    continue
                has_wave = True
                latest_invalid = bool(inv)
                if inv:
                    y_valid.append(float("nan"))
                    y_invalid.append(0.0)
                else:
                    y_valid.append(value)
                    y_invalid.append(float("nan"))
            self.wave_curves[item["id"]].setData(x_data, y_valid)
            self.wave_invalid_curves[item["id"]].setData(x_data, y_invalid)
            if has_wave and latest_invalid:
                self.wave_plots[item["id"]].setTitle(f"{item['title']} : DATA_INVALID")
            else:
                self.wave_plots[item["id"]].setTitle(item["title"])
            self.wave_plots[item["id"]].setXRange(0, wave_window, padding=0.0)

    @staticmethod
    def _split_valid_invalid(y_data, invalid_data):
        y_valid, y_invalid = [], []
        for value, inv in zip(y_data, invalid_data):
            if isinstance(value, float) and math.isnan(value):
                y_valid.append(value)
                y_invalid.append(value)
            elif inv:
                y_valid.append(float("nan"))
                y_invalid.append(0.0)
            else:
                y_valid.append(value)
                y_invalid.append(float("nan"))
        return y_valid, y_invalid

    # ── Capture finish / error ────────────────────────────────────────

    def on_finished(self, output_file):
        self.update_plots()
        self.sim_idle_timer.stop()
        self._notes_autosave_timer.stop()
        self.notes_manager.end_session()
        self.capture_started_monotonic = None
        self.log(f"Capture finished. File: {output_file}")
        self._set_capture_button_state("idle")
        self._refresh_review_button_state()
        self._allow_close_during_capture = False
        self._update_mode_ui()

    def on_error(self, error_message):
        self.sim_idle_timer.stop()
        self._notes_autosave_timer.stop()
        self.notes_manager.end_session()
        self.capture_started_monotonic = None
        self.log(f"ERROR: {error_message}")
        self._set_capture_button_state("idle")
        self._refresh_review_button_state()
        self._allow_close_during_capture = False
        self._update_mode_ui()
