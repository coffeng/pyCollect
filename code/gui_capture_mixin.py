"""Capture, port scan, and control server mixin for PyCollectQtWindow."""
import json
import time
from pathlib import Path

import serial.tools.list_ports as list_ports
from PyQt5 import QtCore, QtGui, QtWidgets

import pycollect
from collector_worker import CollectorWorker
from local_control import LocalControlServer
from port_scan_worker import PortScanWorker


class _GuiCaptureMixin:
    """Port scanning, capture start/stop, waveform request catalog,
    control server handlers, and runtime config persistence."""

    # ── Port helpers ──────────────────────────────────────────────────

    def _selected_port(self) -> str:
        idx = self.port_combo.currentIndex()
        if idx < 0:
            return ""
        data = self.port_combo.itemData(idx)
        if data:
            return str(data)
        return str(self.port_combo.currentText() or "").strip()

    def refresh_ports(self):
        if self.port_scan_active:
            return
        self.port_scan_active = True
        self.refresh_ports_btn.setEnabled(False)
        self.refresh_ports_btn.setText("Scanning...")

        current = self._selected_port()
        self.port_combo.clear()
        ports = sorted(
            {p.device for p in list(list_ports.comports())},
            key=lambda name: (
                int(name[3:]) if name.upper().startswith("COM") and name[3:].isdigit() else -1,
                name,
            ),
            reverse=True,
        )
        for port in ports:
            self.port_combo.addItem(port, userData=port)
        if current:
            idx = self.port_combo.findData(current)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)
        self.log(f"Ports: {', '.join(ports) if ports else 'none'} (scanning...)")

        if self.port_scan_worker is not None and self.port_scan_worker.isRunning():
            self.port_scan_worker.request_stop()
            self.port_scan_worker.wait(timeout=2000)
        self.port_scan_worker = PortScanWorker(parent=self)
        self.port_scan_worker.results_signal.connect(self._on_port_scan_results)
        self.port_scan_worker.finished_signal.connect(self._on_port_scan_finished)
        self.port_scan_worker.error_signal.connect(self._on_port_scan_error)
        self.port_scan_worker.start()

    def _on_port_scan_results(self, results):
        self.port_scan_results = results
        success_pairs = results.get("success_pairs", [])
        for i in range(self.port_combo.count()):
            port = self.port_combo.itemData(i) or self.port_combo.itemText(i)
            is_success = any(p == port for p, b in success_pairs)
            if is_success:
                self.port_combo.setItemData(i, QtGui.QBrush(QtGui.QColor(100, 200, 100)), QtCore.Qt.BackgroundRole)
                self.port_combo.setItemData(i, QtGui.QColor(0, 0, 0), QtCore.Qt.ForegroundRole)
            else:
                self.port_combo.setItemData(i, None, QtCore.Qt.BackgroundRole)
                self.port_combo.setItemData(i, None, QtCore.Qt.ForegroundRole)
        for i in range(self.baud_combo.count()):
            try:
                baud = int(self.baud_combo.itemText(i))
            except (ValueError, TypeError):
                baud = None
            current_port = self._selected_port()
            is_success = any(p == current_port and b == baud for p, b in success_pairs)
            if is_success:
                self.baud_combo.setItemData(i, QtGui.QBrush(QtGui.QColor(100, 200, 100)), QtCore.Qt.BackgroundRole)
                self.baud_combo.setItemData(i, QtGui.QColor(0, 0, 0), QtCore.Qt.ForegroundRole)
            else:
                self.baud_combo.setItemData(i, None, QtCore.Qt.BackgroundRole)
                self.baud_combo.setItemData(i, None, QtCore.Qt.ForegroundRole)
        self.log(f"Port scan complete: {len(success_pairs)} monitor(s) detected")

    def _on_port_scan_finished(self):
        self.port_scan_active = False
        self.refresh_ports_btn.setEnabled(True)
        self.refresh_ports_btn.setText("Refresh")
        self.refresh_ports_btn.setToolTip(self.port_scan_results.get("tooltip_text", "No results"))

    def _on_port_scan_error(self, error_msg):
        self.port_scan_active = False
        self.refresh_ports_btn.setEnabled(True)
        self.refresh_ports_btn.setText("Refresh")
        self.log(f"Port scan error: {error_msg}")
        self.refresh_ports_btn.setToolTip(f"Error: {error_msg}")

    def _on_port_combo_changed(self, index):
        if not self.port_scan_results or not self.port_scan_results.get("success_pairs"):
            return
        success_pairs = self.port_scan_results.get("success_pairs", [])
        current_port = self._selected_port()
        for i in range(self.baud_combo.count()):
            try:
                baud = int(self.baud_combo.itemText(i))
            except (ValueError, TypeError):
                baud = None
            is_success = any(p == current_port and b == baud for p, b in success_pairs)
            if is_success:
                self.baud_combo.setItemData(i, QtGui.QBrush(QtGui.QColor(100, 200, 100)), QtCore.Qt.BackgroundRole)
                self.baud_combo.setItemData(i, QtGui.QColor(0, 0, 0), QtCore.Qt.ForegroundRole)
            else:
                self.baud_combo.setItemData(i, None, QtCore.Qt.BackgroundRole)
                self.baud_combo.setItemData(i, None, QtCore.Qt.ForegroundRole)

    def _on_tab_changed(self, index):
        if index == 1 and self._is_capture_running():
            self.cr_tabs.blockSignals(True)
            self.cr_tabs.setCurrentIndex(0)
            self.cr_tabs.blockSignals(False)
            self.log("Stop capture before switching to Review")

    # ── Capture lifecycle ─────────────────────────────────────────────

    def start_capture(self, broadcast=True):
        port = self._selected_port()
        if not port:
            self.log("No COM port selected")
            return
        if self.worker is not None and self.worker.isRunning():
            self.log("Capture already running")
            return

        self._sync_output_target_from_inputs()
        target_file = Path(self.output_name)
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.log(f"ERROR: cannot create output folder: {exc}")
            return
        if target_file.exists():
            resolved = pycollect.resolve_non_overwriting_path(target_file)
            self.save_filename_edit.setText(Path(resolved).name)
            self._sync_output_target_from_inputs()
            self.log(
                "Target file exists; using timestamped filename: "
                + Path(self.output_name).name
            )

        self._clear_review_state()
        self._clear_runtime_buffers()
        self.update_plots(force=True)

        duration = self.duration_spin.value()
        baudrate = int(self.baud_combo.currentText() or "19200")
        self.worker = CollectorWorker(
            port=port,
            duration_sec=duration,
            all_trend_defs=self.all_trend_defs,
            all_wave_defs=self.all_wave_defs,
            trend_defs=self.trend_defs,
            wave_defs=self.wave_defs,
            baudrate=baudrate,
            trend_interval_sec=float(self.trend_interval_spin.value()),
            output_name=self.output_name,
            simulation_mode=self.simulation_mode,
            no_rtscts=self.no_rtscts,
            alarm_start_hex=self.alarm_start_hex,
            alarm_stop_hex=self.alarm_stop_hex,
            alarm_start_hex_list=self.alarm_start_hex_list,
            alarm_stop_hex_list=self.alarm_stop_hex_list,
        )
        self.worker.update_requested_wave_rows(self.wave_requested_rows)
        self.worker.package_signal.connect(self.on_package)
        self.worker.wave_mapping_signal.connect(self.on_wave_mapping)
        self.worker.status_signal.connect(self.log)
        self.worker.file_status_signal.connect(self.on_file_status)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.error_signal.connect(self.on_error)

        self._set_capture_button_state("armed")

        wave_fs_log = ", ".join(
            [f"{item['label']}={item['sample_hz']:.1f}Hz" for item in self.wave_defs]
        )
        self.log(
            f"Starting capture on {port}@{baudrate}, duration={duration}s, "
            f"config={self.config['path']}, fs: {wave_fs_log}"
        )
        self._update_graph_header()
        self.worker.start()
        if broadcast:
            self._broadcast_to_peers("start")

    def on_file_status(self, state, output_file):
        if state == "appending":
            self._set_file_save_status("blue", output_file)
            self._set_capture_button_state("recording")
            self.log(f"Appending to: {Path(output_file).name}")
            self.notes_manager.start_session(output_file)
            if not self._notes_autosave_timer.isActive():
                self._notes_autosave_timer.start()
            return
        if state == "closed":
            self._set_file_save_status("green", output_file)
            self.review_file_edit.setText(str(output_file))
            self._sync_review_source_from_input()
            self.last_active_drc_file = str(output_file)
            self.log(f"Closed file: {Path(output_file).name}")

    def stop_capture(self, broadcast=True):
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.log("Stop requested")
            if broadcast:
                self._broadcast_to_peers("stop")

    def _is_capture_running(self):
        return bool(self.worker is not None and self.worker.isRunning())

    def _unlock_all_sections_for_stop(self):
        sections = self._all_lockable_sections()
        if not any(s.is_locked for s in sections):
            return False
        for section in sections:
            section.set_locked(False)
        self._lock_btn.setText("🔓  Lock collapsed sections")
        self._persist_lock_state()
        return True

    def _prepare_stop_focus_on_close_attempt(self):
        unlocked = self._unlock_all_sections_for_stop()
        if unlocked:
            self.log("Unlocked sections. Use Stop Monitoring before closing.")
        if self._is_capture_running():
            self.capture_toggle_btn.setDefault(True)
            self.capture_toggle_btn.setFocus(QtCore.Qt.ActiveWindowFocusReason)
            self.log("Monitoring is active. Press Enter on Stop Monitoring first.")
        else:
            self.log("Monitoring is active. Stop monitoring before closing.")

    # ── Mode UI helpers ───────────────────────────────────────────────

    def _set_capture_button_state(self, state):
        if state == "recording":
            self.capture_toggle_btn.setText("STOP")
            self.capture_toggle_btn.setStyleSheet(self._wave_button_style_for_state("red"))
            self.capture_toggle_btn.setDefault(True)
        elif state == "armed":
            self.capture_toggle_btn.setText("START")
            self.capture_toggle_btn.setStyleSheet(self._wave_button_style_for_state("green"))
            self.capture_toggle_btn.setDefault(False)
        else:
            self.capture_toggle_btn.setText("START")
            self.capture_toggle_btn.setStyleSheet(self._wave_button_style_for_state("blue"))
            self.capture_toggle_btn.setDefault(False)
        if hasattr(self, "review_btn"):
            self._refresh_review_button_state()
        if hasattr(self, "mode_badge_label"):
            self._update_mode_ui()

    def _update_mode_ui(self):
        if self.review_mode:
            review_name = Path(self.review_file_path).name if self.review_file_path else ""
            text = "Mode: Reviewing" + (f" ({review_name})" if review_name else "")
            self.mode_badge_label.setText(text)
            self.mode_badge_label.setStyleSheet(
                "padding:4px 8px;border-radius:4px;"
                "font-weight:600;background:#ffd166;color:#1a1a1a;"
            )
            self.exit_review_btn.setVisible(True)
            self.apply_capture_view_btn.setEnabled(False)
            self.apply_capture_view_btn.setToolTip("Exit review to apply capture selection")
            if hasattr(self, "cr_tabs"):
                self.cr_tabs.setCurrentIndex(1)
            return

        port_text = self._selected_port()
        if self._is_capture_running() and port_text:
            mode_text = f"Mode: Live Capture ({port_text})"
        elif port_text:
            mode_text = f"Mode: Capture Setup ({port_text})"
        else:
            mode_text = "Mode: Capture Setup"
        self.mode_badge_label.setText(mode_text)
        self.mode_badge_label.setStyleSheet(
            "padding:4px 8px;border-radius:4px;"
            "font-weight:600;background:#00d4ff;color:#0a1428;"
        )
        self.exit_review_btn.setVisible(False)
        self.apply_capture_view_btn.setEnabled(True)
        self.apply_capture_view_btn.setToolTip("Refresh live view using capture selections")
        if hasattr(self, "cr_tabs"):
            self.cr_tabs.setCurrentIndex(0)

    def _on_capture_toggle_clicked(self):
        if self._is_capture_running():
            self.stop_capture()
        else:
            self.start_capture()

    def _on_apply_capture_view_clicked(self):
        if self.review_mode:
            self.log("Exit review before applying capture selection")
            return
        self._rebuild_trend_plots()
        self._rebuild_wave_plots()
        self.update_plots(force=True)
        self.update_plots()
        self.log("Applied capture selection to live view")
        self._update_mode_ui()

    # ── Wave request catalog ──────────────────────────────────────────

    def _displayed_wave_row_ids(self):
        return {int(item["row_identifier"]) for item in self.wave_defs}

    def _is_actively_appending(self):
        if self.current_file_state != "blue":
            return False
        if self.worker is None:
            return False
        try:
            return self.worker.isRunning()
        except RuntimeError:
            return False

    def _wave_request_button_state(self, row_id):
        requested = row_id in self.wave_requested_rows
        last_seen_any = self.wave_last_seen_by_row.get(row_id)
        has_data = (
            last_seen_any is not None
            and (time.monotonic() - float(last_seen_any)) <= self.WAVE_REQUEST_TIMEOUT_SEC
        )
        if self.simulation_mode:
            if requested and has_data:
                return "green"
            elif not requested and has_data:
                return "blue"
            elif requested and not has_data:
                return "yellow"
            else:
                return "default"

        last_rx = self.wave_last_received_at.get(row_id)
        age = (time.monotonic() - last_rx) if last_rx is not None else None
        receiving = age is not None and age <= self.WAVE_REQUEST_TIMEOUT_SEC
        appending = self._is_actively_appending()
        missing_timeout = False
        if requested and last_rx is None and appending and self.capture_started_monotonic is not None:
            missing_timeout = (
                (time.monotonic() - self.capture_started_monotonic)
                > self.WAVE_REQUEST_TIMEOUT_SEC
            )
        if requested and receiving:
            return "green"
        if requested and last_rx is None and missing_timeout:
            return "red"
        if requested and last_rx is None:
            return "blue"
        if requested and not receiving:
            return "red"
        if not requested and receiving:
            return "yellow"
        return "default"

    def _apply_wave_request_button_style(self, row_id):
        if self._is_closing:
            return
        btn = self.wave_request_buttons.get(row_id)
        if btn is None:
            return
        try:
            state = self._wave_request_button_state(row_id)
            btn.setStyleSheet(self._wave_button_style_for_state(state))
            btn.setProperty("color_state", state)
            btn.blockSignals(True)
            btn.setChecked(row_id in self.wave_requested_rows)
            btn.blockSignals(False)
        except RuntimeError:
            pass

    def _refresh_wave_request_button_states(self):
        if self._is_closing:
            return
        for row_id in list(self.wave_request_buttons.keys()):
            self._apply_wave_request_button_style(row_id)

    def _on_wave_request_clicked(self, row_id, checked):
        row_id = int(row_id)
        displayed = self._displayed_wave_row_ids()
        appending = self._is_actively_appending()
        if (
            (not self.simulation_mode)
            and row_id in displayed
            and not checked
            and appending
        ):
            state = self._wave_request_button_state(row_id)
            if state != "red":
                btn = self.wave_request_buttons.get(row_id)
                if btn is not None:
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                self.log(f"Wave row #{row_id} stays requested while active")
                return
        if checked:
            self.wave_requested_rows.add(row_id)
            self.wave_user_unrequested_rows.discard(row_id)
            self.log(f"Requested wave row #{row_id}")
        else:
            self.wave_requested_rows.discard(row_id)
            self.wave_user_unrequested_rows.add(row_id)
            self.log(f"Cleared request for wave row #{row_id}")
        if self.worker is not None and self.worker.isRunning():
            self.worker.update_requested_wave_rows(self.wave_requested_rows)
        self._rebuild_wave_defs()
        self._rebuild_wave_plots()
        self._apply_wave_request_button_style(row_id)

    # ── Control server ────────────────────────────────────────────────

    def _on_control_stop(self):
        QtCore.QTimer.singleShot(0, self._apply_control_stop)
        return "stopping capture"

    def _apply_control_stop(self):
        self.log("Remote stop requested")
        self.stop_capture(broadcast=False)

    def _on_control_start(self):
        QtCore.QTimer.singleShot(0, self._apply_control_start)
        return "starting capture"

    def _apply_control_start(self):
        if self._is_capture_running():
            self.log("Remote start ignored (already running)")
            return
        self.log("Remote start requested")
        self.start_capture(broadcast=False)

    def _discover_peers(self):
        if self.control_port <= 0:
            return
        self._peer_ports = []
        for offset in range(1, 6):
            for peer in [self.control_port + offset, self.control_port - offset]:
                if peer > 0 and LocalControlServer.is_peer_listening(peer):
                    self._peer_ports.append(peer)
                    self.log(f"Peer instance detected on port {peer}")

    def _broadcast_to_peers(self, command):
        self._discover_peers()
        for peer_port in self._peer_ports:
            try:
                resp = LocalControlServer.send_command(peer_port, command, timeout=0.1)
                if resp:
                    self.log(f"Peer :{peer_port} {command} -> {resp}")
            except Exception:
                pass

    def _on_control_status(self):
        running = self._is_capture_running()
        return (
            f"running={running} "
            f"port={self._selected_port()} "
            f"baud={self.baud_combo.currentText()}"
        )

    def _on_simulation_idle_timeout(self):
        self.log("No package for 10 seconds in simulation mode")

    # ── Runtime config save ───────────────────────────────────────────

    def _save_runtime_config(self):
        cfg_path = Path(self.config.get("path", ""))
        if not cfg_path:
            return
        data = {}
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data.setdefault("signal_sources", {})
        data.setdefault("ui", {})
        data.setdefault("channels", {})
        data["ui"].setdefault("connection", {})
        data["ui"].setdefault("simulator", {})
        data["ui"]["duration_sec"] = int(self.duration_spin.value())
        data["ui"]["trend_window_sec"] = int(self.hr_window_spin.value())
        data["ui"]["wave_window_sec"] = float(self.ecg_window_spin.value())
        data["ui"]["output_directory"] = str(self.output_directory)
        data["ui"]["output_filename"] = str(self.output_filename)
        data["ui"]["review_file"] = str(self.review_source_file)
        data["ui"]["last_active_drc_file"] = str(self.last_active_drc_file)
        data["ui"]["connection"]["baudrate"] = int(self.baud_combo.currentText() or "19200")
        data["ui"]["graph_split_ratio"] = float(self.graph_split_ratio)
        data["ui"]["simulator"]["speed_multiplier"] = float(self.sim_speed_spin.value())
        data["channels"]["trends"] = [
            {"row_identifier": int(item["row_identifier"])} for item in self.trend_defs
        ]
        data["channels"]["waves"] = [
            {"row_identifier": int(item["row_identifier"])} for item in self.wave_defs
        ]
        cfg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _start_wave_request_state_timer(self):
        if not self.wave_request_state_timer.isActive():
            self.wave_request_state_timer.start()
