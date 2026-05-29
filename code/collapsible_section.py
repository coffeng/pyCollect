"""Collapsible sidebar section widget for pyCollect GUI."""
from PyQt5 import QtCore, QtWidgets


class CollapsibleSection(QtWidgets.QWidget):
    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        self.title = title
        self.toggle_btn = QtWidgets.QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow
        )
        self.toggle_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self.toggle_btn.setStyleSheet(
            "QToolButton { text-align: left; padding-left: 2px; }"
        )

        self.is_locked = False

        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 6, 8, 6)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.toggle_btn)
        root.addWidget(self.content)

        self.toggle_btn.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked):
        if self.is_locked and checked:
            self.toggle_btn.blockSignals(True)
            self.toggle_btn.setChecked(False)
            self.toggle_btn.blockSignals(False)
            return
        self.content.setVisible(checked)
        self.toggle_btn.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        self._update_lock_appearance()

    def set_locked(self, locked):
        self.is_locked = locked
        self._update_lock_appearance()

    def _update_lock_appearance(self):
        base_align = "QToolButton { text-align: left; padding-left: 2px;"
        if self.is_locked:
            self.toggle_btn.setStyleSheet(
                base_align + " color: #888888; background: #1a1a1a; }"
            )
        else:
            self.toggle_btn.setStyleSheet(base_align + " }")
        self._apply_content_lock_state()

    def _apply_content_lock_state(self):
        for widget in self._get_editable_widgets():
            if self.is_locked:
                widget.setEnabled(False)
                if isinstance(widget, QtWidgets.QLabel):
                    widget.setStyleSheet("color: #888888;")
                elif isinstance(
                    widget,
                    (QtWidgets.QLineEdit, QtWidgets.QSpinBox, QtWidgets.QComboBox),
                ):
                    widget.setStyleSheet("color: #888888; background: #1a1a1a;")
            else:
                widget.setEnabled(True)
                if isinstance(widget, QtWidgets.QLabel):
                    widget.setStyleSheet("")
                elif isinstance(
                    widget,
                    (QtWidgets.QLineEdit, QtWidgets.QSpinBox, QtWidgets.QComboBox),
                ):
                    widget.setStyleSheet("")

    def _get_editable_widgets(self):
        widgets = []
        for widget in self.content.findChildren(QtWidgets.QWidget):
            if isinstance(
                widget,
                (
                    QtWidgets.QLabel,
                    QtWidgets.QLineEdit,
                    QtWidgets.QSpinBox,
                    QtWidgets.QComboBox,
                    QtWidgets.QPushButton,
                ),
            ):
                widgets.append(widget)
        return widgets
