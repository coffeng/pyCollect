# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\100014430\\Documents\\GitHub\\Enterprise\\pyCollect\\code\\pycollect.py'],
    pathex=[],
    binaries=[],
    datas=[('config', 'config'), ('assets', 'assets')],
    hiddenimports=['PyQt5.sip', 'PyQt5.QtCore', 'PyQt5.QtWidgets', 'PyQt5.QtGui', 'pyqtgraph', 'serial', 'serial.tools', 'serial.tools.list_ports'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'PySide2', 'PyQt6', 'shiboken6', 'IPython', 'jupyter', 'zmq', 'scipy', 'pyarrow', 'numba', 'llvmlite', 'tensorflow', 'torch', 'tkinter', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pyCollect-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\100014430\\Documents\\GitHub\\Enterprise\\pyCollect\\version_info.txt',
    icon=['C:\\Users\\100014430\\Documents\\GitHub\\Enterprise\\pyCollect\\assets\\icon.ico'],
)
