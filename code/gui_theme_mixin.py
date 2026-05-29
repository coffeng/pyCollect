"""Theme and color mixin for PyCollectQtWindow."""
import pyqtgraph as pg

from config_loader import _normalize_signal_key


class _GuiThemeMixin:
    """Color, style, and theme helper methods.

    Mixed into PyCollectQtWindow; accesses self.colors and self.config.
    """

    def _cfg_color(self, section, key, fallback):
        section_data = self.colors.get(section, {})
        value = section_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    def _alarm_color_css(self, alarm_color):
        color_map = {0: "#d7dde8", 1: "#ffffff", 2: "#ffd166", 3: "#ff4757"}
        if isinstance(alarm_color, int):
            return color_map.get(alarm_color, color_map[3])
        return self._cfg_color("text", "alarm", "#ff4757")

    def _resolve_signal_color(self, section, item, fallback):
        palette = self.colors.get(section, {})
        if not isinstance(palette, dict):
            return fallback

        aliases = {
            "hr": "heart_rate",
            "heartrate": "heart_rate",
            "pr": "heart_rate",
            "sys": "systolic",
            "dia": "diastolic",
        }

        candidates = [
            item.get("id", ""),
            item.get("label", ""),
            item.get("title", ""),
        ]
        for raw in candidates:
            key = _normalize_signal_key(raw)
            if not key:
                continue
            for lookup in (key, aliases.get(key, "")):
                if lookup and lookup in palette:
                    value = palette.get(lookup)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        default_color = palette.get("default")
        if isinstance(default_color, str) and default_color.strip():
            return default_color.strip()
        return fallback

    def _style_plot_widget(self, plot):
        plot_bg = self._cfg_color("plot", "background", "#edf1f5")
        grid_color = self._cfg_color("plot", "grid", "#98a4b4")
        border_color = self._cfg_color("plot", "border", "#9aa5b3")
        axis_text_color = self._cfg_color("text", "primary", "#ffffff")
        plot.setBackground(plot_bg)
        plot.showGrid(x=True, y=True, alpha=0.25)
        grid_pen = pg.mkPen(grid_color, width=1)
        plot.getAxis("left").setPen(grid_pen)
        plot.getAxis("bottom").setPen(grid_pen)
        axis_text_pen = pg.mkPen(axis_text_color, width=1)
        plot.getAxis("left").setTextPen(axis_text_pen)
        plot.getAxis("bottom").setTextPen(axis_text_pen)
        plot.getViewBox().setBorder(pg.mkPen(border_color, width=1))

    def _wave_button_style_for_state(self, state):
        status = self.colors.get("status", {})
        buttons = self.colors.get("buttons", {})
        button_states = self.colors.get("button_statuses", {})
        secondary_text = self._cfg_color("text", "secondary", "#222222")
        normal_bg = buttons.get("normal_bg") or "transparent"
        normal_text = buttons.get("normal_text") or secondary_text

        state_cfg = button_states.get(state, {})
        default_cfg = button_states.get("default", {})

        def _pick_color(cfg, key):
            value = cfg.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None

        if state == "green":
            bg = _pick_color(state_cfg, "bg") or status.get("active") or "#3ab36b"
            fg = _pick_color(state_cfg, "text") or "#ffffff"
        elif state == "blue":
            bg = _pick_color(state_cfg, "bg") or buttons.get("active_bg") or "#2b83f6"
            fg = _pick_color(state_cfg, "text") or buttons.get("active_text") or "#ffffff"
        elif state == "yellow":
            bg = _pick_color(state_cfg, "bg") or status.get("warning") or "#ffa500"
            fg = _pick_color(state_cfg, "text") or "#1a1a1a"
        elif state == "red":
            bg = _pick_color(state_cfg, "bg") or status.get("alarm") or "#d6352b"
            fg = _pick_color(state_cfg, "text") or "#ffffff"
        else:
            bg = (
                _pick_color(state_cfg, "bg")
                or _pick_color(default_cfg, "bg")
                or normal_bg
            )
            fg = (
                _pick_color(state_cfg, "text")
                or _pick_color(default_cfg, "text")
                or normal_text
            )
        return f"background:{bg};color:{fg};font-weight:600;"

    def _apply_pcs_theme(self):
        sidebar_bg = self._cfg_color("sidebar", "background", "#d6dde6")
        sidebar_text = self._cfg_color("sidebar", "text", "#111111")
        sidebar_border = self._cfg_color("sidebar", "border", "#b8c0cb")
        primary_text = self._cfg_color("text", "primary", "#111111")
        secondary_text = self._cfg_color("text", "secondary", "#3e4a5a")
        buttons_normal_bg = self._cfg_color("buttons", "normal_bg", "#c7ced8")
        buttons_normal_text = self._cfg_color("buttons", "normal_text", primary_text)
        buttons_hover_bg = self._cfg_color("buttons", "hover_bg", "#bec7d2")
        splitter_bg = self._cfg_color("plot", "grid", "#98a4b4")
        inputs_bg = self._cfg_color("plot", "background", "#f1f4f7")

        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background: {sidebar_bg};
                color: {primary_text};
                font-size: 12px;
            }}
            QFrame {{
                background: {sidebar_bg};
                border: 1px solid {sidebar_border};
            }}
            QLabel {{ color: {primary_text}; }}
            QToolButton {{
                background: {buttons_normal_bg};
                color: {buttons_normal_text};
                border: 1px solid {sidebar_border};
                border-radius: 3px;
                font-weight: 600;
                padding: 6px;
                text-align: left;
            }}
            QToolButton:hover {{ background: {buttons_hover_bg}; }}
            QComboBox, QSpinBox, QDoubleSpinBox, QPushButton {{
                background: {inputs_bg};
                color: {sidebar_text};
                border: 1px solid {sidebar_border};
                border-radius: 3px;
                padding: 4px;
            }}
            QPlainTextEdit {{
                background: {inputs_bg};
                color: {secondary_text};
                border: 1px solid {sidebar_border};
            }}
            QSplitter::handle {{
                background: {splitter_bg};
                width: 6px;
            }}
            """
        )
        pg.setConfigOption("background", self._cfg_color("plot", "background", "#edf1f5"))
        pg.setConfigOption("foreground", primary_text)

    def _save_state_colors(self, state):
        button_states = self.colors.get("button_statuses", {})
        buttons = self.colors.get("buttons", {})
        state_cfg = button_states.get(state, {})
        default_cfg = button_states.get("default", {})

        def _pick(cfg, key):
            value = cfg.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None

        bg = (
            _pick(state_cfg, "bg")
            or _pick(default_cfg, "bg")
            or buttons.get("normal_bg")
            or "#1f2d3d"
        )
        fg = (
            _pick(state_cfg, "text")
            or _pick(default_cfg, "text")
            or buttons.get("normal_text")
            or "#ffffff"
        )
        return bg, fg
