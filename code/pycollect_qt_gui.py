"""pyCollect Qt GUI — main window module.

Architecture: PyCollectQtWindow inherits from six mixin classes that
provide logically grouped method sets, plus QtWidgets.QMainWindow.

    _GuiThemeMixin      — color / style helpers
    _GuiBuildMixin      — _build_ui, _connect_signals, Notes UI
    _GuiReviewMixin     — review load, CSV conversion, file-status
    _GuiCatalogMixin    — trend/wave catalog, graph rebuild
    _GuiCaptureMixin    — capture start/stop, port scan, wave catalog
    _GuiPlotMixin       — on_package, update_plots, on_finished

New: Notes/Markers feature (PS_COLLECT_UI_009 / PS_COLLECT_UI_010).
     CaseNotesManager persists timestamped notes as a .txt sidecar.
"""
import argparse
import ctypes
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
from PyQt5 import QtCore, QtGui, QtWidgets

import drc_2_csv  # noqa: F401 — imported for side-effects used by CsvConversionWorker
import pycollect
from local_control import LocalControlServer

from config_loader import (
    DEFAULT_CONFIG,
    SignalConfigError,
    _compact_label_start,
    _normalize_signal_key,
    _resolve_icon_path,
    _runtime_search_roots,
    _startup_log,
    _startup_log_path,
    load_signal_config,
)
from collapsible_section import CollapsibleSection
from collector_worker import CollectorWorker
from csv_conversion_worker import CsvConversionWorker
from notes_manager import CaseNotesManager
from port_scan_worker import PortScanWorker

from gui_theme_mixin import _GuiThemeMixin
from gui_build_mixin import _GuiBuildMixin
from gui_review_mixin import _GuiReviewMixin
from gui_catalog_mixin import _GuiCatalogMixin
from gui_capture_mixin import _GuiCaptureMixin
from gui_plot_mixin import _GuiPlotMixin


class PyCollectQtWindow(
    _GuiThemeMixin,
    _GuiBuildMixin,
    _GuiReviewMixin,
    _GuiCatalogMixin,
    _GuiCaptureMixin,
    _GuiPlotMixin,
    QtWidgets.QMainWindow,
):
    def __init__(
        self,
        config,
        output_name="",
        initial_port=None,
        autostart=False,
        simulation_mode=False,
        initial_duration=None,
        debug_stdout=False,
        control_port=0,
        no_rtscts=False,
        auto_open_last_review=False,
        instance_id=1,
    ):
        super().__init__()
        from collections import deque

        self._instance_id = instance_id
        self.setWindowTitle("pyCollect Interactive Viewer")
        self.resize(1300, 760)

        self.config = config
        self.config_path = Path(config.get("path", ""))
        self.colors = config.get("colors", {})
        self.all_trend_defs = config["all_trend_defs"]
        self.all_wave_defs = config["all_wave_defs"]
        self.output_name = output_name
        self.output_directory = ""
        self.output_filename = ""
        self.review_source_file = str(
            config.get("initial_review_file", "") or ""
        ).strip()
        self.last_active_drc_file = str(
            config.get("initial_last_active_drc_file", "") or ""
        ).strip()
        self.auto_open_last_review = bool(auto_open_last_review)
        self.autostart = autostart
        self.simulation_mode = simulation_mode
        self.debug_stdout = debug_stdout
        self.control_port = int(control_port or 0)
        self.no_rtscts = bool(no_rtscts)
        self._is_closing = False
        self._allow_close_during_capture = False
        self._peer_ports = []
        self.trend_defs = config["trend_defs"]
        self.wave_defs = config["wave_defs"]
        self.positive_trend_rows = set()
        self.positive_wave_rows = set()

        self.wave_requested_rows = set()
        self.wave_user_unrequested_rows = set()
        self.wave_last_received_at = {}
        self.wave_request_buttons = {}
        self.WAVE_REQUEST_TIMEOUT_SEC = 5.0
        self.capture_started_monotonic = None
        self.first_record_header_utc = None
        self.last_record_header_utc = None
        self.wave_last_seen_monotonic = {}
        self.wave_last_seen_by_row = {}
        self._last_logged_available_waves = None
        self._last_trend_unix = None
        self.last_alarm_text = "none"
        self.last_alarm_color = None
        self.last_logged_alarm_text = "none"
        self.last_logged_alarm_color = None
        self.last_alarm_seen_monotonic = None
        self.alarm_start_hex, self.alarm_stop_hex, self.alarm_start_hex_list, self.alarm_stop_hex_list = (
            self._resolve_alarm_commands()
        )
        self.current_output_file = ""
        self.current_file_state = "default"
        self.review_mode = False
        self.review_file_path = ""
        self.review_records = []
        self.review_record_index = 0
        self.review_trend_history_by_row = {}
        self.review_wave_history_by_id = {}
        self.review_first_header_utc = None
        self.review_last_header_utc = None
        self.csv_worker = None
        self.csv_convert_in_progress = False

        self.port_scan_worker = None
        self.port_scan_results = {"success_pairs": [], "tooltip_text": ""}
        self.port_scan_active = False

        self.invalid_detected_total = 0
        self.invalid_wave_points_total = 0
        self.invalid_trend_points_total = 0
        self._last_invalid_log_monotonic = 0.0
        self._last_no_invalid_log_monotonic = 0.0

        self.worker = None
        self.logical_now_sec = 0.0
        self._in_splitter_adjust = False
        self.graph_split_ratio = float(config.get("initial_split_ratio", 0.5))

        self.trend_buffers = {item["id"]: deque() for item in self.trend_defs}
        self.trend_history_by_row = {}
        self.wave_buffers = {item["id"]: deque() for item in self.wave_defs}
        self.wave_cursors = {item["id"]: None for item in self.wave_defs}
        for item in self.all_wave_defs:
            self.wave_last_seen_by_row[int(item["row_identifier"])] = None

        self.trend_plots = {}
        self.trend_curves = {}
        self.trend_invalid_curves = {}
        self.wave_plots = {}
        self.wave_curves = {}
        self.wave_invalid_curves = {}
        self.trend_catalog_buttons = {}

        self.sim_idle_timer = QtCore.QTimer(self)
        self.sim_idle_timer.setSingleShot(True)
        self.sim_idle_timer.setInterval(10000)
        self.sim_idle_timer.timeout.connect(self._on_simulation_idle_timeout)

        self.wave_request_state_timer = QtCore.QTimer(self)
        self.wave_request_state_timer.setInterval(1000)
        self.wave_request_state_timer.timeout.connect(
            self._refresh_wave_request_button_states
        )
        self.wave_request_state_timer.timeout.connect(
            self._refresh_trend_button_states
        )

        self.invalid_pen = pg.mkPen("#9aa0a6", width=2)

        # ── Notes/Markers feature (PS_COLLECT_UI_009/010) ──────────────
        self.notes_manager = CaseNotesManager(config.get("notes", {}))
        self._notes_autosave_timer = QtCore.QTimer(self)
        self._notes_autosave_timer.setInterval(
            int(self.notes_manager.autosave_interval_sec) * 1000
        )
        self._notes_autosave_timer.timeout.connect(
            self.notes_manager.autosave_if_needed
        )

        self._init_output_target()
        self._apply_pcs_theme()
        self._build_ui()
        self._connect_signals()
        self._set_capture_button_state("idle")
        self._restore_lock_state()
        self.refresh_ports()

        if initial_duration is not None:
            self.duration_spin.setValue(initial_duration)

        if initial_port:
            port_index = self.port_combo.findData(initial_port)
            if port_index < 0:
                port_index = self.port_combo.findText(initial_port)
            if port_index >= 0:
                self.port_combo.setCurrentIndex(port_index)
                self.log(f"Preselected port from CLI: {initial_port}")
            else:
                self.log(f"CLI port not found: {initial_port}")

        if self.simulation_mode and self.autostart:
            self.conn_section.toggle_btn.setChecked(False)

        if autostart and initial_port:
            QtCore.QTimer.singleShot(0, self.start_capture)
        elif self.auto_open_last_review:
            QtCore.QTimer.singleShot(
                0, self._auto_open_last_review_if_available
            )

        self.wave_request_state_timer.start()
        for row_id in self._displayed_wave_row_ids():
            self.wave_requested_rows.add(int(row_id))
        self._refresh_wave_request_button_states()
        self._rebuild_trend_plots()
        self._rebuild_wave_plots()

        self.control_server = LocalControlServer(
            name="gui",
            port=self.control_port,
            on_stop=self._on_control_stop,
            on_status=self._on_control_status,
            on_start=self._on_control_start,
            logger=self.log,
        )
        if not self.control_server.start() and self.control_port > 0:
            self.log(
                f"Control port {self.control_port} in use "
                "(another instance may be running)"
            )
        self._discover_peers()
        self._apply_instance_appearance()

    # ── Instance helpers ──────────────────────────────────────────────

    def _apply_instance_appearance(self):
        if self._instance_id <= 1:
            return
        geo = self.geometry()
        self.move(geo.x() + 60, geo.y() + 60)

    def _resolve_alarm_commands(self):
        def _pick(*paths):
            for path in paths:
                cur = self.config
                ok = True
                for key in path:
                    if not isinstance(cur, dict) or key not in cur:
                        ok = False
                        break
                    cur = cur[key]
                if ok and isinstance(cur, str) and cur.strip():
                    return cur.strip()
            return ""

        start_hex = _pick(
            ("protocol", "alarm_start_hex"),
            ("protocol", "commands", "alarm_start_hex"),
        )
        stop_hex = _pick(
            ("protocol", "alarm_stop_hex"),
            ("protocol", "commands", "alarm_stop_hex"),
        )
        xmit_status_hex = _pick(
            ("protocol", "commands", "alarm_xmit_status_hex"),
            ("protocol", "commands", "alarm_cmd_0_hex"),
        )
        enter_diff_hex = _pick(
            ("protocol", "commands", "alarm_enter_diffmode_hex"),
            ("protocol", "commands", "alarm_cmd_2_hex"),
        )
        exit_diff_hex = _pick(
            ("protocol", "commands", "alarm_exit_diffmode_hex"),
            ("protocol", "commands", "alarm_cmd_3_hex"),
        )
        start_list = [f for f in [xmit_status_hex, enter_diff_hex] if f]
        stop_list = [f for f in [exit_diff_hex] if f]
        if not start_list and start_hex:
            start_list = [start_hex]
        if not stop_list and stop_hex:
            stop_list = [stop_hex]
        return start_hex, stop_hex, start_list, stop_list

    # ── Close ─────────────────────────────────────────────────────────

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange:
            is_full = bool(self.windowState() & (
                QtCore.Qt.WindowMaximized | QtCore.Qt.WindowFullScreen
            ))
            self._set_kiosk_mode(is_full)
        super().changeEvent(event)

    def _set_kiosk_mode(self, enabled):
        self.sidebar.setVisible(not enabled)

    def closeEvent(self, event):
        if self._is_capture_running() and not self._allow_close_during_capture:
            event.ignore()
            self._prepare_stop_focus_on_close_attempt()
            return

        self._is_closing = True
        for timer in [
            self.wave_request_state_timer,
            self.sim_idle_timer,
            self._notes_autosave_timer,
        ]:
            try:
                timer.stop()
            except Exception:
                pass

        self.notes_manager.end_session()

        try:
            if getattr(self, "worker", None) and self.worker.isRunning():
                self.worker.request_stop()
                self.worker.wait(5000)
        except Exception:
            pass
        try:
            if getattr(self, "csv_worker", None) and self.csv_worker.isRunning():
                self.csv_worker.wait(5000)
        except Exception:
            pass
        try:
            self.control_server.stop()
        except Exception:
            pass
        self._save_runtime_config()
        super().closeEvent(event)


def main():
    _startup_log(
        f"qt main start frozen={getattr(sys, 'frozen', False)} argv={sys.argv!r}"
    )
    raw_argv = list(sys.argv[1:])

    parser = argparse.ArgumentParser(
        description="Interactive Qt GUI for pycollect capture."
    )
    parser.add_argument("--port", default="", help="Preselect this port and autostart capture.")
    parser.add_argument("--duration", type=int, default=None, help="Optional duration in seconds.")
    parser.add_argument("--config", default="", help="Path to JSON config file.")
    parser.add_argument("--output", default="", help="Output filename (.drc).")
    parser.add_argument(
        "--simulation-mode", action="store_true",
        help="Enable simulator-friendly behavior.",
    )
    parser.add_argument("--debug-stdout", action="store_true", help="Mirror GUI log to stdout.")
    parser.add_argument("--control-port", type=int, default=0, help="Localhost TCP control port.")
    parser.add_argument("--baud", type=int, default=None, help="Override serial baud rate.")
    parser.add_argument("--no-rtscts", action="store_true", help="Disable RTS/CTS flow control.")
    args = parser.parse_args()

    cfg_path = args.config.strip() if args.config else None

    instance_number = 1
    if args.control_port > 0:
        base_port = args.control_port
        while LocalControlServer.is_peer_listening(args.control_port):
            args.control_port += 1
            instance_number = args.control_port - base_port + 1
        if instance_number > 1:
            _startup_log(
                f"Peer(s) detected; using control port {args.control_port}"
                f" (instance {instance_number})"
            )

    instance_suffix = f"_{instance_number}" if instance_number > 1 else ""
    if instance_suffix and not cfg_path:
        try:
            base_config = load_signal_config(None)
            base_path = Path(base_config["path"])
            alt_path = base_path.with_name(base_path.stem + instance_suffix + base_path.suffix)
            if not alt_path.exists():
                import shutil
                shutil.copy2(str(base_path), str(alt_path))
                _startup_log(f"Created instance config: {alt_path.name}")
            cfg_path = str(alt_path)
            _startup_log(f"Using config: {cfg_path}")
        except Exception:
            _startup_log("Could not derive _2 config; using default")

    try:
        config = load_signal_config(cfg_path)
    except Exception as exc:
        msg = f"Failed to load signal config:\n{exc}"
        _startup_log(msg)
        print(msg, file=sys.stderr)
        try:
            app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
            QtWidgets.QMessageBox.critical(None, "pyCollect - Config Error", msg)
            app.processEvents()
        except Exception:
            pass
        sys.exit(1)

    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "GEHealthCare.pyCollect"
            )
        except Exception:
            pass

    if args.baud is not None and args.baud in (19200, 115200):
        config["initial_baudrate"] = args.baud

    app = QtWidgets.QApplication(sys.argv)
    icon_path = _resolve_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))
    pg.setConfigOptions(antialias=True)

    initial_duration = args.duration if args.duration is not None else config["initial_duration"]
    default_launch = len(raw_argv) == 0

    win = PyCollectQtWindow(
        config=config,
        output_name=args.output.strip(),
        initial_port=args.port.strip() or None,
        autostart=bool(args.port.strip()),
        simulation_mode=args.simulation_mode,
        initial_duration=max(5, int(initial_duration)),
        debug_stdout=args.debug_stdout,
        control_port=args.control_port,
        no_rtscts=args.no_rtscts,
        auto_open_last_review=default_launch,
        instance_id=instance_number,
    )
    if icon_path is not None:
        win.setWindowIcon(QtGui.QIcon(str(icon_path)))
    win.show()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _startup_log("FATAL\n" + traceback.format_exc())
        raise
