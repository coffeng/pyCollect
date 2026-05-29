"""Catalog, graph rebuild, and plot-window mixin for PyCollectQtWindow."""
import math
from collections import deque
from datetime import datetime

import pyqtgraph as pg
from PyQt5 import QtWidgets


class _GuiCatalogMixin:
    """Trend/wave catalog buttons, graph rebuild, sync helpers."""

    # ── Trend catalog ─────────────────────────────────────────────────

    def _on_trend_catalog_clicked(self, row_id, checked):
        row_id = int(row_id)
        selected_row_ids = [int(d["row_identifier"]) for d in self.trend_defs]
        all_trend_by_row = {int(item["row_identifier"]): item for item in self.all_trend_defs}
        if checked and row_id not in selected_row_ids:
            item = all_trend_by_row.get(row_id)
            if item:
                selected = dict(item)
                selected["id"] = f"t_{row_id}"
                self.trend_defs.append(selected)
                if selected["id"] not in self.trend_buffers:
                    self.trend_buffers[selected["id"]] = deque()
                self._sort_trend_defs_by_catalog()
                self._sync_all_trend_buffers()
                self._rebuild_trend_plots()
        elif not checked and row_id in selected_row_ids:
            self.trend_defs = [
                d for d in self.trend_defs
                if int(d["row_identifier"]) != row_id
            ]
            self._sort_trend_defs_by_catalog()
            self._rebuild_trend_plots()
        self._apply_trend_button_style(row_id)

    def _apply_trend_button_style(self, row_id):
        btn = self.trend_catalog_buttons.get(row_id)
        if btn is None:
            return
        selected = row_id in {int(d["row_identifier"]) for d in self.trend_defs}
        has_positive = row_id in self.positive_trend_rows
        if selected and has_positive:
            bg, fg = "#2fa44f", "#ffffff"
        elif selected and not has_positive:
            bg, fg = "#80c88a", "#1a2a1a"
        elif not selected and has_positive:
            bg, fg = "#00d4ff", "#0a1428"
        else:
            bg, fg = "", ""
        try:
            if bg:
                btn.setStyleSheet(f"background-color:{bg}; color:{fg};")
            else:
                btn.setStyleSheet("")
        except RuntimeError:
            pass

    def _refresh_trend_button_states(self):
        if self._is_closing:
            return
        for row_id in list(self.trend_catalog_buttons.keys()):
            self._apply_trend_button_style(row_id)

    def _filter_trend_catalog(self, text):
        query = text.strip().lower()
        grid = self._trend_catalog_grid
        for _, _, btn in self._trend_catalog_items:
            grid.removeWidget(btn)
        col = row_idx = 0
        for _rid, label, btn in self._trend_catalog_items:
            if query and query not in label.lower():
                btn.setVisible(False)
            else:
                btn.setVisible(True)
                grid.addWidget(btn, row_idx, col)
                col += 1
                if col >= 3:
                    col = 0
                    row_idx += 1

    def _filter_wave_catalog(self, text):
        query = text.strip().lower()
        grid = self._wave_catalog_grid
        for _, _, btn in self._wave_catalog_items:
            grid.removeWidget(btn)
        col = row_idx = 0
        for _rid, label, btn in self._wave_catalog_items:
            if query and query not in label.lower():
                btn.setVisible(False)
            else:
                btn.setVisible(True)
                grid.addWidget(btn, row_idx, col)
                col += 1
                if col >= 3:
                    col = 0
                    row_idx += 1

    # ── Graph rebuild ─────────────────────────────────────────────────

    def _calc_graph_min_height(self):
        try:
            screen_h = QtWidgets.QApplication.primaryScreen().size().height()
        except Exception:
            screen_h = 1080
        return max(80, screen_h // 10)

    def _rebuild_trend_plots(self):
        self._sort_trend_defs_by_catalog()
        for item_id, plot in list(self.trend_plots.items()):
            self.trends_layout.removeWidget(plot)
            plot.setParent(None)
            plot.deleteLater()
        self.trend_plots.clear()
        self.trend_curves.clear()
        self.trend_invalid_curves.clear()
        min_h = self._calc_graph_min_height()
        trend_fallbacks = ["#2b83f6", "#24b47e", "#b38ddb", "#6fd3ff"]
        for idx, item in enumerate(self.trend_defs):
            plot = pg.PlotWidget(title=item["title"])
            self._style_plot_widget(plot)
            plot.setLabel("left", text=item["label"], units=item["unit"])
            plot.setMinimumHeight(min_h)
            curve = plot.plot(
                pen=pg.mkPen(
                    self._resolve_signal_color(
                        "trends", item,
                        trend_fallbacks[idx % len(trend_fallbacks)],
                    ),
                    width=2,
                )
            )
            invalid_curve = plot.plot(pen=self.invalid_pen)
            self.trend_plots[item["id"]] = plot
            self.trend_curves[item["id"]] = curve
            self.trend_invalid_curves[item["id"]] = invalid_curve
            self.trends_layout.addWidget(plot)
        self.update_plots()
        self._refresh_trend_button_states()

    def _sort_trend_defs_by_catalog(self):
        rank_by_row = {
            int(item["row_identifier"]): idx
            for idx, item in enumerate(self.all_trend_defs)
        }
        self.trend_defs = sorted(
            self.trend_defs,
            key=lambda item: rank_by_row.get(int(item.get("row_identifier", -1)), 10**9),
        )

    def _rebuild_wave_plots(self):
        for item_id, plot in list(self.wave_plots.items()):
            self.waves_layout.removeWidget(plot)
            plot.setParent(None)
            plot.deleteLater()
        self.wave_plots.clear()
        self.wave_curves.clear()
        self.wave_invalid_curves.clear()
        min_h = self._calc_graph_min_height()
        wave_fallbacks = ["#f23c3c", "#ff8c42", "#ff5a7a", "#f6d743"]
        for idx, item in enumerate(self.wave_defs):
            plot = pg.PlotWidget(title=item["title"])
            self._style_plot_widget(plot)
            plot.setLabel("left", text=item["label"], units=item["unit"])
            plot.setMinimumHeight(min_h)
            curve = plot.plot(
                pen=pg.mkPen(
                    self._resolve_signal_color(
                        "waveforms", item,
                        wave_fallbacks[idx % len(wave_fallbacks)],
                    ),
                    width=1.5,
                )
            )
            invalid_curve = plot.plot(pen=self.invalid_pen)
            self.wave_plots[item["id"]] = plot
            self.wave_curves[item["id"]] = curve
            self.wave_invalid_curves[item["id"]] = invalid_curve
            self.waves_layout.addWidget(plot)
        self.update_plots()

    def _rebuild_wave_defs(self):
        all_wave_by_row = {
            int(item["row_identifier"]): item for item in self.all_wave_defs
        }
        new_wave_defs = []
        for row_id in sorted(self.wave_requested_rows):
            item = all_wave_by_row.get(row_id)
            if item is None:
                continue
            d = dict(item)
            d["id"] = f"w_{row_id}"
            new_wave_defs.append(d)
        for item in new_wave_defs:
            if item["id"] not in self.wave_buffers:
                self.wave_buffers[item["id"]] = deque()
                self.wave_cursors[item["id"]] = None
        self.wave_defs = new_wave_defs
        if self.worker is not None and self.worker.isRunning():
            self.worker.update_wave_defs(self.wave_defs)

    def _sync_all_trend_buffers(self):
        for item in self.trend_defs:
            row_id = item["row_identifier"]
            buf_id = item["id"]
            if buf_id not in self.trend_buffers:
                self.trend_buffers[buf_id] = deque()
            history = self.trend_history_by_row.get(row_id)
            if history is None:
                self.trend_buffers[buf_id].clear()
            else:
                self.trend_buffers[buf_id] = deque(history)

    # ── Logging helper ────────────────────────────────────────────────

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        if self.debug_stdout:
            try:
                print(line, flush=True)
            except Exception:
                pass
        if self._is_closing:
            return
        try:
            self.status_box.appendPlainText(line)
        except RuntimeError:
            pass

    # ── Splitter ──────────────────────────────────────────────────────

    def _split_ratios(self):
        sizes = self.graph_splitter.sizes()
        total = max(1, sum(sizes))
        return float(sizes[0]) / float(total), float(sizes[1]) / float(total), total

    def _apply_graph_split_ratio(self, ratio):
        ratio = min(0.9, max(0.1, float(ratio)))
        total = max(1, sum(self.graph_splitter.sizes()))
        left_px = int(total * ratio)
        right_px = total - left_px
        self._in_splitter_adjust = True
        self.graph_splitter.setSizes([left_px, right_px])
        self._in_splitter_adjust = False

    def _effective_windows(self):
        trend_window = max(1.0, float(self.hr_window_spin.value()))
        wave_window = max(1.0, float(self.ecg_window_spin.value()))
        return trend_window, wave_window

    def on_splitter_moved(self, _pos, _index):
        if self._in_splitter_adjust:
            return
        left_ratio, _right_ratio, total = self._split_ratios()
        clamped_ratio = min(0.9, max(0.1, left_ratio))
        if abs(clamped_ratio - left_ratio) > 1e-6:
            self._in_splitter_adjust = True
            left_px = int(total * clamped_ratio)
            self.graph_splitter.setSizes([left_px, total - left_px])
            self._in_splitter_adjust = False
        self.graph_split_ratio = clamped_ratio
        self._save_runtime_config()
        self.update_plots()
