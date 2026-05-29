#!/usr/bin/env python3
"""Test GUI port scan integration with PortScanWorker."""

import sys
from pathlib import Path
from PyQt5 import QtWidgets, QtCore
import time

# Add code dir to path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from pycollect_qt_gui import PortScanWorker


class TestWindow(QtWidgets.QMainWindow):
    """Minimal test window for port scan integration."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Port Scan Integration Test")
        self.resize(400, 300)
        
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        # Port combo
        layout.addWidget(QtWidgets.QLabel("Available Ports:"))
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.addItems(["COM1", "COM2", "COM3"])
        layout.addWidget(self.port_combo)
        
        # Baud combo
        layout.addWidget(QtWidgets.QLabel("Baud Rate:"))
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(["19200", "115200"])
        layout.addWidget(self.baud_combo)
        
        # Refresh button
        self.refresh_btn = QtWidgets.QPushButton("Refresh Ports")
        self.refresh_btn.setToolTip("Click to scan for S/5 monitors")
        layout.addWidget(self.refresh_btn)
        
        # Results display
        layout.addWidget(QtWidgets.QLabel("Scan Results:"))
        self.results_text = QtWidgets.QPlainTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        layout.addWidget(self.results_text)
        
        # Status label
        self.status_label = QtWidgets.QLabel("Ready")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        self.setCentralWidget(widget)
        
        # Port scan state
        self.port_scan_worker = None
        self.port_scan_active = False
        self.port_scan_results = {"success_pairs": [], "tooltip_text": ""}
        
        # Connect signals
        self.refresh_btn.clicked.connect(self.start_port_scan)
        
        print("Test window created successfully")
        print(f"Refresh button exists: {self.refresh_btn is not None}")
        print(f"Port combo exists: {self.port_combo is not None}")
        print(f"Baud combo exists: {self.baud_combo is not None}")
    
    def start_port_scan(self):
        """Start port scan in background."""
        if self.port_scan_active:
            self.results_text.setPlainText("Scan already in progress...")
            return
        
        self.port_scan_active = True
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Scanning...")
        self.status_label.setText("Scanning for S/5 monitors...")
        self.results_text.setPlainText("Starting port scan...\n")
        
        # Start worker
        if self.port_scan_worker is not None and self.port_scan_worker.isRunning():
            self.port_scan_worker.request_stop()
            self.port_scan_worker.wait(timeout=2000)
        
        self.port_scan_worker = PortScanWorker(parent=self)
        self.port_scan_worker.results_signal.connect(self._on_port_scan_results)
        self.port_scan_worker.finished_signal.connect(self._on_port_scan_finished)
        self.port_scan_worker.error_signal.connect(self._on_port_scan_error)
        self.port_scan_worker.start()
    
    def _on_port_scan_results(self, results):
        """Handle port scan results."""
        self.port_scan_results = results
        tooltip_text = results.get("tooltip_text", "No results")
        success_pairs = results.get("success_pairs", [])
        
        self.results_text.setPlainText(tooltip_text)
        self.refresh_btn.setToolTip(tooltip_text)
        self.status_label.setText(f"Found {len(success_pairs)} monitor(s)")
        
        # Apply green highlighting
        for i in range(self.port_combo.count()):
            port = self.port_combo.itemText(i)
            is_success = any(p == port for p, b in success_pairs)
            if is_success:
                self.port_combo.setItemData(i, QtCore.Qt.green, QtCore.Qt.ForegroundRole)
        
        for i in range(self.baud_combo.count()):
            baud_text = self.baud_combo.itemText(i)
            try:
                baud = int(baud_text)
            except ValueError:
                baud = None
            
            port = self.port_combo.currentText()
            is_success = any(p == port and b == baud for p, b in success_pairs)
            if is_success:
                self.baud_combo.setItemData(i, QtCore.Qt.green, QtCore.Qt.ForegroundRole)
    
    def _on_port_scan_finished(self):
        """Called when scan finishes."""
        self.port_scan_active = False
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh Ports")
        self.status_label.setText("Scan complete")
        print("Port scan finished")
    
    def _on_port_scan_error(self, error_msg):
        """Called if scan encounters an error."""
        self.port_scan_active = False
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh Ports")
        self.status_label.setText(f"Error: {error_msg}")
        self.results_text.setPlainText(f"Error: {error_msg}")
        print(f"Port scan error: {error_msg}")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = TestWindow()
    window.show()
    
    print("Test window displayed")
    print("Click 'Refresh Ports' to test the port scan worker")
    print("Press Ctrl+C to exit\n")
    
    # Auto-start scan after a short delay for testing
    def auto_scan():
        print("Auto-starting port scan in 2 seconds...")
        QtCore.QTimer.singleShot(2000, window.start_port_scan)
        # Exit after 15 seconds
        QtCore.QTimer.singleShot(15000, app.quit)
    
    QtCore.QTimer.singleShot(100, auto_scan)
    
    sys.exit(app.exec_())
