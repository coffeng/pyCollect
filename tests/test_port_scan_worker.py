#!/usr/bin/env python3
"""Quick test of PortScanWorker integration."""

import sys
from pathlib import Path

# Add code dir to path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

# Test that the PortScanWorker can be imported
try:
    from pycollect_qt_gui import PortScanWorker
    print("✓ PortScanWorker imported successfully")
except ImportError as e:
    print(f"✗ Failed to import PortScanWorker: {e}")
    sys.exit(1)

# Test that it's a QThread subclass
from PyQt5 import QtCore
if issubclass(PortScanWorker, QtCore.QThread):
    print("✓ PortScanWorker is a QThread subclass")
else:
    print("✗ PortScanWorker is not a QThread subclass")
    sys.exit(1)

# Test that it has required signals
if hasattr(PortScanWorker, 'results_signal'):
    print("✓ PortScanWorker has results_signal")
else:
    print("✗ PortScanWorker missing results_signal")
    sys.exit(1)

if hasattr(PortScanWorker, 'finished_signal'):
    print("✓ PortScanWorker has finished_signal")
else:
    print("✗ PortScanWorker missing finished_signal")
    sys.exit(1)

# Test that it has required methods
if hasattr(PortScanWorker, 'request_stop'):
    print("✓ PortScanWorker has request_stop method")
else:
    print("✗ PortScanWorker missing request_stop method")
    sys.exit(1)

print("\nAll checks passed! PortScanWorker is properly integrated.")
