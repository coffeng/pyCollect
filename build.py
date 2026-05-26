"""
build.py  —  Build pyCollect.exe with PyInstaller
=================================================
Usage:
    python build.py            # increments build number, builds exe
    python build.py --no-sign  # skip code signing prompt

Produces:
    dist/pyCollect.exe         standalone Windows executable
    pyCollect_Setup.exe        Inno Setup installer (if ISCC is on PATH)

Requires:
    pip install pyinstaller pillow pyqt5 pyqtgraph pyserial
    Inno Setup 6  (https://jrsoftware.org/isinfo.php) for the installer step
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.absolute()
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
ICON_PATH = ROOT / "assets" / "icon.ico"
VERSION_FILE = ROOT / "version_info.txt"
SPEC_FILE = ROOT / "pyCollect.spec"
MAIN_PY = ROOT / "code" / "pycollect.py"
ISS_FILE = ROOT / "pyCollect.iss"

APP_NAME = "pyCollect"


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _read_version() -> str:
    if not VERSION_FILE.exists():
        return "1.0.0"
    m = re.search(r"FileVersion', '([\d.]+)'", VERSION_FILE.read_text())
    return m.group(1) if m else "1.0.0"


def _increment_version(v: str) -> str:
    parts = [int(x) for x in v.split(".")]
    parts[-1] += 1
    return ".".join(str(x) for x in parts)


def _write_version(version: str) -> None:
    now = datetime.datetime.now()
    fv = version.replace(".", ",") + ", 0"
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({fv}),
    prodvers=({fv}),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'GE HealthCare'),
        StringStruct('FileDescription', 'pyCollect Bedside Monitor Data Collector'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('ProductVersion', '{version}'),
        StringStruct('ProductName', 'pyCollect'),
        StringStruct('BuildDate', '{now.strftime("%Y-%m-%d")}'),
        StringStruct('BuildTime', '{now.strftime("%H:%M:%S")}')]
        )
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    VERSION_FILE.write_text(content, encoding="utf-8")
    print(f"Version info written: {version}  ({now.strftime('%Y-%m-%d %H:%M:%S')})")


# ---------------------------------------------------------------------------
# Icon helper
# ---------------------------------------------------------------------------

def _ensure_icon() -> bool:
    if ICON_PATH.exists():
        print(f"Icon: {ICON_PATH}")
        return True
    print(f"Warning: icon not found at {ICON_PATH}")
    return False


# ---------------------------------------------------------------------------
# PyInstaller build
# ---------------------------------------------------------------------------

def _clean_spec() -> None:
    if SPEC_FILE.exists():
        SPEC_FILE.unlink()
        print("Removed old spec file.")


def _build_exe(has_icon: bool) -> bool:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--windowed",
        f"--name={APP_NAME}",
        # Bundle config directory so the frozen app can find signal definitions
        "--add-data=config;config",
        # Bundle icon preview for potential future splash use
        f"--version-file={VERSION_FILE}",
        # PyQt5 / pyqtgraph imports
        "--hidden-import=PyQt5.sip",
        "--hidden-import=PyQt5.QtCore",
        "--hidden-import=PyQt5.QtWidgets",
        "--hidden-import=PyQt5.QtGui",
        "--hidden-import=pyqtgraph",
        "--hidden-import=serial",
        "--hidden-import=serial.tools",
        "--hidden-import=serial.tools.list_ports",
        # Exclude heavy packages not used by this app
        "--exclude-module=PySide6",
        "--exclude-module=PySide2",
        "--exclude-module=PyQt6",
        "--exclude-module=shiboken6",
        "--exclude-module=IPython",
        "--exclude-module=jupyter",
        "--exclude-module=zmq",
        "--exclude-module=scipy",
        "--exclude-module=pyarrow",
        "--exclude-module=numba",
        "--exclude-module=llvmlite",
        "--exclude-module=tensorflow",
        "--exclude-module=torch",
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
    ]

    if has_icon:
        cmd.append(f"--icon={ICON_PATH}")

    cmd.append(str(MAIN_PY))

    print(f"\nRunning PyInstaller (entry: {MAIN_PY.relative_to(ROOT)})")
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=False)
        exe = DIST_DIR / f"{APP_NAME}.exe"
        if exe.exists():
            size_mb = exe.stat().st_size / 1024 / 1024
            print(f"\nBuild successful: {exe}  ({size_mb:.1f} MB)")
            return True
        else:
            print("Build finished but exe not found.")
            return False
    except subprocess.CalledProcessError as exc:
        print(f"PyInstaller failed (exit {exc.returncode})")
        return False


# ---------------------------------------------------------------------------
# Inno Setup installer
# ---------------------------------------------------------------------------

def _build_installer() -> bool:
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if not iscc:
        # Common install location
        iscc_path = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
        if iscc_path.exists():
            iscc = str(iscc_path)
    if not iscc:
        print("Inno Setup (ISCC) not found on PATH — skipping installer.")
        return False
    if not ISS_FILE.exists():
        print(f"{ISS_FILE.name} not found — skipping installer.")
        return False

    print(f"\nRunning Inno Setup: {iscc} {ISS_FILE.name}")
    try:
        subprocess.run([iscc, str(ISS_FILE)], cwd=ROOT, check=True)
        setup_exe = ROOT / "pyCollect_Setup.exe"
        if setup_exe.exists():
            size_mb = setup_exe.stat().st_size / 1024 / 1024
            print(f"Installer: {setup_exe}  ({size_mb:.1f} MB)")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"Inno Setup failed (exit {exc.returncode})")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Build pyCollect.exe")
    parser.add_argument("--no-sign", action="store_true", help="Skip code signing prompt")
    parser.add_argument("--no-installer", action="store_true", help="Skip Inno Setup step")
    parser.add_argument("--version", help="Override version number (e.g. 1.2.3)")
    args = parser.parse_args()

    # Version
    prev = _read_version()
    version = args.version if args.version else _increment_version(prev)
    _write_version(version)
    print(f"Building {APP_NAME} v{version}")

    # Icon
    has_icon = _ensure_icon()

    # Clean old spec
    _clean_spec()

    # Build exe
    if not _build_exe(has_icon):
        return 1

    # Optional: sign exe
    if not args.no_sign:
        exe = DIST_DIR / f"{APP_NAME}.exe"
        try:
            resp = input("\nSign pyCollect.exe with signtool? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = "n"
        if resp in {"y", "yes"}:
            sign_cmd = [
                "signtool", "sign",
                "/tr", "http://timestamp.digicert.com",
                "/td", "SHA256",
                "/fd", "SHA256",
                str(exe),
            ]
            try:
                subprocess.run(sign_cmd, check=True)
                print("Signed successfully.")
            except Exception as exc:
                print(f"Signing failed: {exc}")

    # Build installer
    if not args.no_installer:
        _build_installer()

    return 0


if __name__ == "__main__":
    sys.exit(main())
