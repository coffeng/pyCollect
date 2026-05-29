"""UI construction mixin for PyCollectQtWindow."""
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from collapsible_section import CollapsibleSection
from config_loader import _compact_label_start


class _GuiBuildMixin:
    """_build_ui and _connect_signals methods.

    Mixed into PyCollectQtWindow.
    """

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.sidebar = QtWidgets.QScrollArea()
        self.sidebar.setFixedWidth(340)
        self.sidebar.setWidgetResizable(True)
        self.sidebar.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.sidebar.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.sidebar.setFrameShape(QtWidgets.QFrame.StyledPanel)

        self.sidebar_content = QtWidgets.QWidget()
        self.sidebar_content.setMaximumWidth(340)
        left = QtWidgets.QVBoxLayout(self.sidebar_content)
        left.setContentsMargins(6, 8, 6, 8)
        left.setSpacing(8)

        title = QtWidgets.QLabel("Bedside Monitor Workflow")
        title.setStyleSheet(
            "font-size: 16px; font-weight: 600;"
            f"color:{self._cfg_color('text', 'accent', '#111111')};"
        )
        left.addWidget(title)

        self.mode_badge_label = QtWidgets.QLabel("Mode: Capture Setup")
        self.mode_badge_label.setVisible(False)

        def _hint(text):
            label = QtWidgets.QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(
                "font-size: 11px;"
                f"color:{self._cfg_color('text', 'secondary', '#3e4a5a')};"
            )
            return label

        accent = self._cfg_color("text", "accent", "#00d4ff")
        panel_bg = self._cfg_color("buttons", "normal_bg", "#1a3a52")
        panel_fg = self._cfg_color("text", "primary", "#e8e8e8")
        self.cr_tabs = QtWidgets.QTabWidget()
        self.cr_tabs.setStyleSheet(
            "QTabWidget::pane {"
            f"  border:1px solid {accent}; border-top:none;"
            f"  background:{panel_bg};"
            "}"
            "QTabBar { qproperty-expanding: true; }"
            "QTabBar::tab {"
            "  padding:6px 16px; font-weight:600; font-size:13px;"
            f"  background:{panel_bg}; color:{panel_fg};"
            f"  border:1px solid {accent}; border-bottom:none;"
            "  border-top-left-radius:4px; border-top-right-radius:4px;"
            "  margin-right:2px;"
            "}"
            "QTabBar::tab:selected {"
            f"  background:{accent}; color:#0a1428;"
            "}"
        )

        # ── CAPTURE TAB ──────────────────────────────────────────────
        capture_page = QtWidgets.QWidget()
        cap_lay = QtWidgets.QVBoxLayout(capture_page)
        cap_lay.setContentsMargins(8, 8, 8, 8)
        cap_lay.setSpacing(6)

        self.capture_toggle_btn = QtWidgets.QPushButton("START")
        self.capture_toggle_btn.setMinimumHeight(34)
        self.capture_toggle_btn.setAutoDefault(True)
        self.capture_toggle_btn.setDefault(False)
        cap_lay.addWidget(self.capture_toggle_btn)

        self.apply_capture_view_btn = QtWidgets.QPushButton(
            "Apply Capture Selection to Live View"
        )
        self.apply_capture_view_btn.setMinimumHeight(28)
        cap_lay.addWidget(self.apply_capture_view_btn)

        self.port_combo = QtWidgets.QComboBox()
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(["19200", "115200"])
        self.baud_combo.setCurrentText(str(self.config["initial_baudrate"]))
        self.refresh_ports_btn = QtWidgets.QPushButton("Refresh")
        cap_lay.addWidget(QtWidgets.QLabel("Source Port"))
        conn_row = QtWidgets.QHBoxLayout()
        conn_row.setContentsMargins(0, 0, 0, 0)
        conn_row.setSpacing(4)
        conn_row.addWidget(self.port_combo, 1)
        conn_row.addWidget(QtWidgets.QLabel("Baud"))
        conn_row.addWidget(self.baud_combo)
        conn_row.addWidget(self.refresh_ports_btn)
        cap_lay.addLayout(conn_row)

        self.dri_level_label = QtWidgets.QLabel("")
        self.dri_level_label.setVisible(False)
        cap_lay.addWidget(self.dri_level_label)

        trend_interval_row = QtWidgets.QHBoxLayout()
        trend_interval_row.setContentsMargins(0, 0, 0, 0)
        trend_interval_row.setSpacing(6)
        trend_interval_row.addWidget(QtWidgets.QLabel("Trend Interval"))
        self.trend_interval_spin = QtWidgets.QSpinBox()
        self.trend_interval_spin.setMinimum(5)
        self.trend_interval_spin.setMaximum(120)
        self.trend_interval_spin.setSingleStep(5)
        self.trend_interval_spin.setValue(
            self.config.get("ui", {}).get("trend_interval_sec", 10)
        )
        self.trend_interval_spin.setSuffix(" sec")
        self.trend_interval_spin.valueChanged.connect(self._on_trend_interval_changed)
        trend_interval_row.addWidget(self.trend_interval_spin)
        trend_interval_row.addStretch()
        cap_lay.addLayout(trend_interval_row)

        cap_lay.addWidget(QtWidgets.QLabel("Recording Folder"))
        self.save_folder_edit = QtWidgets.QLineEdit()
        self.save_folder_edit.setPlaceholderText("Select folder")
        self.save_folder_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed
        )
        self.save_folder_edit.setMinimumWidth(60)
        cap_lay.addWidget(self.save_folder_edit)
        self.save_folder_browse_btn = QtWidgets.QPushButton("Browse...")
        cap_lay.addWidget(self.save_folder_browse_btn)

        cap_lay.addWidget(QtWidgets.QLabel("Recording Filename"))
        self.save_filename_edit = QtWidgets.QLineEdit()
        self.save_filename_edit.setPlaceholderText("record.drc")
        self.save_filename_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed
        )
        self.save_filename_edit.setMinimumWidth(60)
        cap_lay.addWidget(self.save_filename_edit)
        self.save_filename_browse_btn = QtWidgets.QPushButton("Browse...")
        cap_lay.addWidget(self.save_filename_browse_btn)

        self.save_file_name_label = QtWidgets.QLabel("No output file")
        self.save_file_name_label.setVisible(False)

        cap_lay.addWidget(QtWidgets.QLabel("Record Duration (sec)"))
        self.duration_spin = QtWidgets.QSpinBox()
        self.duration_spin.setRange(5, 3600)
        self.duration_spin.setValue(self.config["initial_duration"])
        cap_lay.addWidget(self.duration_spin)
        cap_lay.addStretch()

        self.cr_tabs.addTab(capture_page, "  CAPTURE  ")

        # ── REVIEW TAB ───────────────────────────────────────────────
        review_page = QtWidgets.QWidget()
        rev_lay = QtWidgets.QVBoxLayout(review_page)
        rev_lay.setContentsMargins(8, 8, 8, 8)
        rev_lay.setSpacing(6)

        self.review_btn = QtWidgets.QPushButton("REVIEW")
        self.review_btn.setMinimumHeight(34)
        self.review_btn.setEnabled(False)
        self.exit_review_btn = QtWidgets.QPushButton("Exit Review")
        self.exit_review_btn.setMinimumHeight(28)
        self.exit_review_btn.setVisible(False)
        rev_btn_row = QtWidgets.QHBoxLayout()
        rev_btn_row.setContentsMargins(0, 0, 0, 0)
        rev_btn_row.setSpacing(6)
        rev_btn_row.addWidget(self.review_btn, 1)
        rev_btn_row.addWidget(self.exit_review_btn, 0)
        rev_lay.addLayout(rev_btn_row)

        rev_lay.addWidget(QtWidgets.QLabel("Review File (Input)"))
        self.review_file_edit = QtWidgets.QLineEdit()
        self.review_file_edit.setPlaceholderText("Select a DRC file for review")
        self.review_file_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed
        )
        self.review_file_edit.setMinimumWidth(60)
        rev_lay.addWidget(self.review_file_edit)
        self.review_file_browse_btn = QtWidgets.QPushButton("Open...")
        rev_lay.addWidget(self.review_file_browse_btn)

        self.review_dri_level_label = QtWidgets.QLabel("")
        self.review_dri_level_label.setVisible(False)
        rev_lay.addWidget(self.review_dri_level_label)

        rev_lay.addWidget(
            _hint("Open review file does not change capture output settings.")
        )

        self.convert_csv_btn = QtWidgets.QPushButton("Convert Current DRC to CSV")
        self.convert_csv_btn.setVisible(False)
        self.convert_csv_btn.setEnabled(False)
        self.convert_csv_btn.clicked.connect(self.convert_current_drc_to_csv)
        rev_lay.addWidget(self.convert_csv_btn)

        self.convert_saved_header = QtWidgets.QLabel("Generated CSV Files")
        self.convert_saved_header.setVisible(False)
        rev_lay.addWidget(self.convert_saved_header)

        self.convert_saved_list = QtWidgets.QListWidget()
        self.convert_saved_list.setVisible(False)
        self.convert_saved_list.setMaximumHeight(88)
        self.convert_saved_list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        self.convert_saved_list.setSelectionMode(
            QtWidgets.QAbstractItemView.NoSelection
        )
        self.convert_saved_list.setFocusPolicy(QtCore.Qt.NoFocus)
        self.convert_saved_list.setTextElideMode(QtCore.Qt.ElideLeft)
        rev_lay.addWidget(self.convert_saved_list)

        self.log_file_header = QtWidgets.QLabel("Capture Log")
        self.log_file_header.setVisible(False)
        rev_lay.addWidget(self.log_file_header)
        self.log_file_label = QtWidgets.QLabel("")
        self.log_file_label.setVisible(False)
        self.log_file_label.setWordWrap(True)
        self.log_file_label.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        self.log_file_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
        )
        rev_lay.addWidget(self.log_file_label)
        rev_lay.addStretch()

        self.cr_tabs.addTab(review_page, "  REVIEW  ")
        left.addWidget(self.cr_tabs)

        # Stub lockable sections so _all_lockable_sections works
        self.conn_section = type("_Stub", (), {
            "title": "Monitor Connection",
            "is_locked": False,
            "set_locked": lambda self, v: setattr(self, "is_locked", v),
            "toggle_btn": type("_Btn", (), {
                "isChecked": lambda self: True,
                "setChecked": lambda self, v: None,
                "click": lambda self: None,
                "styleSheet": lambda self: "",
                "setStyleSheet": lambda self, s: None,
            })(),
            "content": type("_Content", (), {
                "isVisible": lambda self: True,
            })(),
        })()
        self.file_save_section = type("_Stub", (), {
            "title": "DRC File Paths",
            "is_locked": False,
            "set_locked": lambda self, v: setattr(self, "is_locked", v),
            "toggle_btn": type("_Btn", (), {
                "isChecked": lambda self: True,
                "setChecked": lambda self, v: None,
                "click": lambda self: None,
                "styleSheet": lambda self: "",
                "setStyleSheet": lambda self, s: None,
            })(),
            "content": type("_Content", (), {
                "isVisible": lambda self: True,
            })(),
        })()

        self.save_folder_edit.setText(self.output_directory)
        self.save_filename_edit.setText(self.output_filename)
        self._sync_output_target_from_inputs()
        self.review_file_edit.setText(self.review_source_file)
        self._sync_review_source_from_input()
        self._set_file_save_status("default", "")

        # ── Screen Setup section ──────────────────────────────────────
        self.view_section = CollapsibleSection("Screen Setup", expanded=True)
        left.addWidget(self.view_section)

        self.hr_window_spin = QtWidgets.QSpinBox()
        self.hr_window_spin.setRange(10, 3600)
        self.hr_window_spin.setValue(int(self.config["initial_trend_window"]))
        self.view_section.content_layout.addWidget(QtWidgets.QLabel("Vitals Window (sec)"))
        self.view_section.content_layout.addWidget(self.hr_window_spin)

        self.ecg_window_spin = QtWidgets.QDoubleSpinBox()
        self.ecg_window_spin.setRange(10.0, 300.0)
        self.ecg_window_spin.setSingleStep(0.5)
        self.ecg_window_spin.setValue(self.config["initial_wave_window"])
        self.view_section.content_layout.addWidget(
            QtWidgets.QLabel("Waveform Window (sec, 10..300)")
        )
        self.view_section.content_layout.addWidget(self.ecg_window_spin)
        self.view_section.content_layout.addWidget(
            _hint("Next: select waveforms and start monitoring.")
        )

        # ── Waveform Selection section ────────────────────────────────
        self.wave_catalog_section = CollapsibleSection(
            "Waveform Selection", expanded=False
        )
        left.addWidget(self.wave_catalog_section)

        if self.simulation_mode:
            wave_hint = (
                "Legend: green = selected + receiving, "
                "blue = receiving but not selected, "
                "yellow = selected but waiting for data."
            )
        else:
            wave_hint = (
                "Legend: green receiving, yellow delayed, red missing, "
                "blue pending request."
            )
        self.wave_catalog_section.content_layout.addWidget(_hint(wave_hint))
        wave_search = QtWidgets.QLineEdit()
        wave_search.setPlaceholderText("Filter waveforms…")
        wave_search.setClearButtonEnabled(True)
        self.wave_catalog_section.content_layout.addWidget(wave_search)

        catalog_scroll = QtWidgets.QScrollArea()
        catalog_scroll.setWidgetResizable(True)
        catalog_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        catalog_scroll.setMinimumHeight(120)
        catalog_scroll.setMaximumHeight(220)
        catalog_inner = QtWidgets.QWidget()
        catalog_grid = QtWidgets.QGridLayout(catalog_inner)
        catalog_grid.setContentsMargins(0, 0, 0, 0)
        catalog_grid.setHorizontalSpacing(4)
        catalog_grid.setVerticalSpacing(4)
        self._wave_catalog_grid = catalog_grid
        self._wave_catalog_items = []

        cols = 3
        for idx, item in enumerate(self.all_wave_defs):
            row_id = int(item["row_identifier"])
            label = item.get("label") or item.get("title") or ""
            btn = QtWidgets.QPushButton(_compact_label_start(label, max_len=8))
            btn.setCheckable(True)
            btn.setToolTip(label)
            btn.setMinimumWidth(90)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            btn.setProperty("row_id", row_id)
            btn.toggled.connect(
                lambda checked, rid=row_id: self._on_wave_request_clicked(rid, checked)
            )
            self.wave_request_buttons[row_id] = btn
            self._wave_catalog_items.append((row_id, label, btn))
            catalog_grid.addWidget(btn, idx // cols, idx % cols)

        catalog_scroll.setWidget(catalog_inner)
        self.wave_catalog_section.content_layout.addWidget(catalog_scroll)
        wave_search.textChanged.connect(self._filter_wave_catalog)

        # ── Trends Selection section ──────────────────────────────────
        self.signal_section = CollapsibleSection("Trends Selection", expanded=True)
        left.addWidget(self.signal_section)

        self.signal_section.content_layout.addWidget(
            _hint(
                "Legend: blue\u00a0=\u00a0has data, green\u00a0=\u00a0selected+data, "
                "light\u00a0green\u00a0=\u00a0selected+no\u00a0data."
            )
        )
        trend_search = QtWidgets.QLineEdit()
        trend_search.setPlaceholderText("Filter trends…")
        trend_search.setClearButtonEnabled(True)
        self.signal_section.content_layout.addWidget(trend_search)

        trend_catalog_scroll = QtWidgets.QScrollArea()
        trend_catalog_scroll.setWidgetResizable(True)
        trend_catalog_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        trend_catalog_scroll.setMinimumHeight(120)
        trend_catalog_scroll.setMaximumHeight(220)
        trend_catalog_inner = QtWidgets.QWidget()
        trend_catalog_grid = QtWidgets.QGridLayout(trend_catalog_inner)
        trend_catalog_grid.setContentsMargins(0, 0, 0, 0)
        trend_catalog_grid.setHorizontalSpacing(4)
        trend_catalog_grid.setVerticalSpacing(4)
        self._trend_catalog_grid = trend_catalog_grid
        self._trend_catalog_items = []

        _trend_cols = 3
        _selected_trend_rows = {int(d["row_identifier"]) for d in self.trend_defs}
        for idx, item in enumerate(self.all_trend_defs):
            row_id = int(item["row_identifier"])
            label = item.get("label") or ""
            btn = QtWidgets.QPushButton(_compact_label_start(label, max_len=8))
            btn.setCheckable(True)
            btn.setChecked(row_id in _selected_trend_rows)
            btn.setToolTip(f"{label} [{item['unit']}]")
            btn.setMinimumWidth(90)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            btn.setProperty("row_id", row_id)
            btn.toggled.connect(
                lambda checked, rid=row_id: self._on_trend_catalog_clicked(rid, checked)
            )
            self.trend_catalog_buttons[row_id] = btn
            self._trend_catalog_items.append((row_id, label, btn))
            trend_catalog_grid.addWidget(btn, idx // _trend_cols, idx % _trend_cols)

        trend_catalog_scroll.setWidget(trend_catalog_inner)
        self.signal_section.content_layout.addWidget(trend_catalog_scroll)
        trend_search.textChanged.connect(self._filter_trend_catalog)

        # ── Case Notes section ────────────────────────────────────────
        self.notes_section = CollapsibleSection("Case Notes", expanded=False)
        left.addWidget(self.notes_section)
        self._build_notes_section(self.notes_section.content_layout, _hint)

        # ── Recorder Output section ───────────────────────────────────
        self.status_section = CollapsibleSection("Recorder Output", expanded=True)
        left.addWidget(self.status_section)
        self.status_box = QtWidgets.QPlainTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumBlockCount(500)
        self.status_section.content_layout.addWidget(self.status_box)

        # ── Advanced section ──────────────────────────────────────────
        self.advanced_section = CollapsibleSection("Advanced", expanded=False)
        left.addWidget(self.advanced_section)

        self._lock_btn = QtWidgets.QPushButton("🔓  Lock collapsed sections")
        self._lock_btn.clicked.connect(self._toggle_all_locks)
        self.advanced_section.content_layout.addWidget(self._lock_btn)
        self.advanced_section.content_layout.addWidget(
            _hint("Locks all currently collapsed sections. Click again to unlock all.")
        )

        self.sim_speed_spin = QtWidgets.QDoubleSpinBox()
        self.sim_speed_spin.setRange(0.05, 1000.0)
        self.sim_speed_spin.setSingleStep(0.05)
        self.sim_speed_spin.setValue(self.config["initial_sim_speed"])
        self.advanced_section.content_layout.addWidget(
            QtWidgets.QLabel("Simulator Replay Speed (x)")
        )
        self.advanced_section.content_layout.addWidget(self.sim_speed_spin)
        self.advanced_section.content_layout.addWidget(
            _hint("Updates ui.simulator.speed_multiplier in config on close.")
        )

        left.addStretch(1)
        self.sidebar.setWidget(self.sidebar_content)
        layout.addWidget(self.sidebar)

        # ── Graph panel ───────────────────────────────────────────────
        self.graph_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.graph_splitter.setChildrenCollapsible(False)

        trends_scroll = QtWidgets.QScrollArea()
        trends_scroll.setWidgetResizable(True)
        trends_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.trends_panel = QtWidgets.QWidget()
        self.trends_layout = QtWidgets.QVBoxLayout(self.trends_panel)
        self.trends_layout.setContentsMargins(0, 0, 0, 0)
        self.trends_layout.setSpacing(4)
        trends_scroll.setWidget(self.trends_panel)

        waves_scroll = QtWidgets.QScrollArea()
        waves_scroll.setWidgetResizable(True)
        waves_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.waves_panel = QtWidgets.QWidget()
        self.waves_layout = QtWidgets.QVBoxLayout(self.waves_panel)
        self.waves_layout.setContentsMargins(0, 0, 0, 0)
        self.waves_layout.setSpacing(4)
        waves_scroll.setWidget(self.waves_panel)

        self.graph_splitter.addWidget(trends_scroll)
        self.graph_splitter.addWidget(waves_scroll)
        self.graph_splitter.setStretchFactor(0, 1)
        self.graph_splitter.setStretchFactor(1, 1)
        self.graph_splitter.setSizes([500, 500])
        self._apply_graph_split_ratio(self.graph_split_ratio)

        self.graph_header = QtWidgets.QFrame()
        self.graph_header.setFrameShape(QtWidgets.QFrame.StyledPanel)
        header_layout = QtWidgets.QVBoxLayout(self.graph_header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(4)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        self.last_record_label = QtWidgets.QLabel("Last record (header UTC): --")
        self.last_record_label.setStyleSheet(
            "font-weight: 600;"
            f"color:{self._cfg_color('text', 'primary', '#111111')};"
        )
        self.elapsed_label = QtWidgets.QLabel("Elapsed (header): --")
        self.elapsed_label.setStyleSheet(
            "font-weight: 600;"
            f"color:{self._cfg_color('text', 'primary', '#111111')};"
        )
        self.recent_waves_label = QtWidgets.QLabel("Waveforms (last 5s): none")
        self.recent_waves_label.setWordWrap(True)
        self.recent_waves_label.setStyleSheet(
            f"color:{self._cfg_color('text', 'secondary', '#23364d')};"
        )
        self.recent_alarm_label = QtWidgets.QLabel("Alarm: none")
        self.recent_alarm_label.setWordWrap(True)
        self.recent_alarm_label.setStyleSheet(
            "font-weight: 600;"
            f"color:{self._cfg_color('text', 'secondary', '#9aa0a6')};"
        )

        top_row.addWidget(self.last_record_label, 0)
        top_row.addWidget(self.elapsed_label, 0)
        top_row.addWidget(self.recent_waves_label, 1)
        header_layout.addLayout(top_row)

        review_row = QtWidgets.QHBoxLayout()
        review_row.setContentsMargins(0, 0, 0, 0)
        review_row.setSpacing(8)
        self.review_slider_title_label = QtWidgets.QLabel("Review Start")
        self.review_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.review_slider.setMinimum(0)
        self.review_slider.setMaximum(0)
        self.review_slider.setSingleStep(1)
        self.review_slider.setPageStep(10)
        self.review_slider_value_label = QtWidgets.QLabel("--")
        self.review_slider_value_label.setMinimumWidth(180)

        self.prev_note_btn = QtWidgets.QPushButton("◀ Note")
        self.prev_note_btn.setFixedWidth(60)
        self.prev_note_btn.setToolTip("Jump to previous case note")
        self.next_note_btn = QtWidgets.QPushButton("Note ▶")
        self.next_note_btn.setFixedWidth(60)
        self.next_note_btn.setToolTip("Jump to next case note")
        review_row.addWidget(self.review_slider_title_label, 0)
        review_row.addWidget(self.prev_note_btn, 0)
        review_row.addWidget(self.review_slider, 1)
        review_row.addWidget(self.next_note_btn, 0)
        review_row.addWidget(self.review_slider_value_label, 0)
        self.review_row_widget = QtWidgets.QWidget()
        self.review_row_widget.setLayout(review_row)
        self.review_row_widget.setVisible(False)
        header_layout.addWidget(self.review_row_widget, 0)
        header_layout.addWidget(self.recent_alarm_label, 0)

        self.graph_panel = QtWidgets.QWidget()
        graph_panel_layout = QtWidgets.QVBoxLayout(self.graph_panel)
        graph_panel_layout.setContentsMargins(0, 0, 0, 0)
        graph_panel_layout.setSpacing(8)
        graph_panel_layout.addWidget(self.graph_header)
        graph_panel_layout.addWidget(self.graph_splitter, 1)

        layout.addWidget(self.graph_panel, 1)
        self._update_graph_header()

    # ── Case Notes section builder ────────────────────────────────────

    def _build_notes_section(self, layout, _hint):
        """Populate the Case Notes collapsible section content."""
        notes_cfg = self.config.get("notes", {})
        templates = list(notes_cfg.get("templates", []))

        layout.addWidget(_hint(
            "Insert timestamped notes during capture. "
            "Saved as a .txt sidecar alongside the DRC file."
        ))

        # Button row: Insert Timestamp | Add Template ▾ | Delete Row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)

        self.notes_insert_btn = QtWidgets.QPushButton("⏱ Timestamp")
        self.notes_insert_btn.setToolTip("Insert new note with current timestamp (Ctrl+T)")
        self.notes_insert_btn.setShortcut("Ctrl+T")
        btn_row.addWidget(self.notes_insert_btn)

        self.notes_template_btn = QtWidgets.QPushButton("Template ▾")
        self.notes_template_btn.setToolTip("Insert a predefined note template")
        self._notes_template_menu = QtWidgets.QMenu(self.notes_template_btn)
        for tmpl in templates:
            action = self._notes_template_menu.addAction(tmpl)
            action.triggered.connect(
                lambda checked, t=tmpl: self._on_notes_template_selected(t)
            )
        self.notes_template_btn.setEnabled(bool(templates))
        self.notes_template_btn.clicked.connect(
            lambda: self._notes_template_menu.exec_(
                self.notes_template_btn.mapToGlobal(
                    self.notes_template_btn.rect().bottomLeft()
                )
            )
        )
        btn_row.addWidget(self.notes_template_btn)

        self.notes_delete_btn = QtWidgets.QPushButton("Delete")
        self.notes_delete_btn.setToolTip("Delete selected row(s)")
        btn_row.addWidget(self.notes_delete_btn)
        layout.addLayout(btn_row)

        # Table: Time | Note
        self.notes_table = QtWidgets.QTableWidget(0, 2)
        self.notes_table.setHorizontalHeaderLabels(["Time", "Note"])
        self.notes_table.horizontalHeader().setStretchLastSection(True)
        self.notes_table.horizontalHeader().setDefaultSectionSize(130)
        self.notes_table.setColumnWidth(0, 130)
        self.notes_table.setMinimumHeight(100)
        self.notes_table.setMaximumHeight(180)
        self.notes_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.notes_table.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self.notes_table.verticalHeader().setVisible(False)
        self.notes_table.setWordWrap(False)
        layout.addWidget(self.notes_table)

        clear_row = QtWidgets.QHBoxLayout()
        clear_row.setContentsMargins(0, 0, 0, 0)
        self.notes_clear_btn = QtWidgets.QPushButton("Clear All")
        self.notes_clear_btn.setToolTip("Remove all notes from this session")
        clear_row.addStretch()
        clear_row.addWidget(self.notes_clear_btn)
        layout.addLayout(clear_row)

        # Wire up buttons
        self.notes_insert_btn.clicked.connect(self._on_notes_insert_clicked)
        self.notes_delete_btn.clicked.connect(self._on_notes_delete_clicked)
        self.notes_clear_btn.clicked.connect(self._on_notes_clear_clicked)
        self.notes_table.itemChanged.connect(self._on_notes_table_item_changed)

    # ── Notes event handlers ──────────────────────────────────────────

    def _on_notes_insert_clicked(self):
        """Insert a new note with the current timestamp."""
        monitor_time = None
        if self.worker is not None and self.worker.isRunning():
            monitor_time = self.worker.last_monitor_time_unix()
        note = self.notes_manager.insert_note("", monitor_time_unix=monitor_time)
        self._notes_append_row(note, focus_text=True)

    def _on_notes_template_selected(self, template_text: str):
        """Insert a note pre-filled with a template string."""
        monitor_time = None
        if self.worker is not None and self.worker.isRunning():
            monitor_time = self.worker.last_monitor_time_unix()
        note = self.notes_manager.insert_note(
            template_text, monitor_time_unix=monitor_time
        )
        self._notes_append_row(note, focus_text=False)

    def _on_notes_delete_clicked(self):
        """Delete currently selected rows."""
        selected_rows = sorted(
            {idx.row() for idx in self.notes_table.selectedIndexes()},
            reverse=True,
        )
        if not selected_rows:
            return
        self.notes_manager.delete_notes(selected_rows)
        self._notes_reload_table()

    def _on_notes_clear_clicked(self):
        """Clear all notes after confirmation."""
        if self.notes_manager.note_count() == 0:
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear Notes",
            "Remove all case notes for this session?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.notes_manager.clear()
            self._notes_reload_table()

    def _on_notes_table_item_changed(self, item):
        """Sync table edits back to the notes manager."""
        row = item.row()
        col = item.column()
        if col == 0:
            self.notes_manager.update_note_time(row, item.text())
        elif col == 1:
            self.notes_manager.update_note_text(row, item.text())

    def _notes_append_row(self, note: dict, focus_text: bool = False):
        """Add one row to the notes table from a note dict."""
        self.notes_table.blockSignals(True)
        r = self.notes_table.rowCount()
        self.notes_table.insertRow(r)
        self.notes_table.setItem(r, 0, QtWidgets.QTableWidgetItem(note.get("display_time", "")))
        self.notes_table.setItem(r, 1, QtWidgets.QTableWidgetItem(note.get("text", "")))
        self.notes_table.blockSignals(False)
        if focus_text:
            self.notes_table.editItem(self.notes_table.item(r, 1))
        self.notes_table.scrollToBottom()

    def _notes_reload_table(self):
        """Rebuild the notes table from the notes manager."""
        self.notes_table.blockSignals(True)
        self.notes_table.setRowCount(0)
        for note in self.notes_manager.all_notes():
            r = self.notes_table.rowCount()
            self.notes_table.insertRow(r)
            self.notes_table.setItem(r, 0, QtWidgets.QTableWidgetItem(note.get("display_time", "")))
            self.notes_table.setItem(r, 1, QtWidgets.QTableWidgetItem(note.get("text", "")))
        self.notes_table.blockSignals(False)

    # ── Signal connections ────────────────────────────────────────────

    def _connect_signals(self):
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        self.port_combo.currentIndexChanged.connect(self._on_port_combo_changed)
        self.cr_tabs.currentChanged.connect(self._on_tab_changed)
        self.capture_toggle_btn.clicked.connect(self._on_capture_toggle_clicked)
        self.review_btn.clicked.connect(self._on_review_clicked)
        self.exit_review_btn.clicked.connect(self._on_exit_review_clicked)
        self.apply_capture_view_btn.clicked.connect(self._on_apply_capture_view_clicked)
        self.review_slider.valueChanged.connect(self._on_review_slider_changed)
        self.hr_window_spin.valueChanged.connect(self.update_plots)
        self.ecg_window_spin.valueChanged.connect(self.update_plots)
        self.graph_splitter.splitterMoved.connect(self.on_splitter_moved)
        self.duration_spin.valueChanged.connect(self._save_runtime_config)
        self.save_folder_browse_btn.clicked.connect(self._on_browse_output_folder)
        self.save_filename_browse_btn.clicked.connect(self._on_browse_output_filename)
        self.review_file_browse_btn.clicked.connect(self._on_browse_review_file)
        self.save_folder_edit.editingFinished.connect(self._on_output_target_edited)
        self.save_filename_edit.editingFinished.connect(self._on_output_target_edited)
        self.review_file_edit.editingFinished.connect(self._on_review_source_edited)
        self.prev_note_btn.clicked.connect(self._on_prev_note_clicked)
        self.next_note_btn.clicked.connect(self._on_next_note_clicked)
