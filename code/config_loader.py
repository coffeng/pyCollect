"""Configuration loading utilities for pyCollect GUI."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_CONFIG = "pycollect_gui_config.json"


# ---------------------------------------------------------------------------
# Startup log helpers
# ---------------------------------------------------------------------------

def _startup_log_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    out_dir = base_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "pycollect_qt_gui_startup.log"


def _startup_log(message: str) -> None:
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _startup_log_path().open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Runtime root resolution
# ---------------------------------------------------------------------------

def _runtime_search_roots():
    roots = []

    if getattr(sys, "frozen", False):
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            local_root = Path(local_appdata) / "pyCollect"
            roots.append(local_root)
            roots.append(local_root / "config")

        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir)
        roots.append(exe_dir / "config")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass).resolve())
            roots.append((Path(meipass).resolve() / "config"))
        roots.append(Path.cwd().resolve())
    else:
        roots.append(Path.cwd().resolve())
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            local_root = Path(local_appdata) / "pyCollect"
            roots.append(local_root)
            roots.append(local_root / "config")
        repo_root = Path(__file__).resolve().parent.parent
        roots.append(repo_root)
        roots.append(repo_root / "config")

    uniq = []
    seen = set()
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(root)
    return uniq


def _resolve_config_path(config_path=""):
    requested = str(config_path or "").strip()
    if requested:
        p = Path(requested)
        if p.is_absolute() and p.exists():
            return p.resolve()
        if p.exists():
            return p.resolve()
        for root in _runtime_search_roots():
            candidate = (root / requested).resolve()
            if candidate.exists():
                return candidate
            if p.name == DEFAULT_CONFIG:
                fallback = (root / DEFAULT_CONFIG).resolve()
                if fallback.exists():
                    return fallback
        return None

    for root in _runtime_search_roots():
        candidate = (root / DEFAULT_CONFIG).resolve()
        if candidate.exists():
            return candidate
    return None


def _config_candidates(config_path=""):
    requested = str(config_path or "").strip()
    candidates = []
    seen = set()

    def _add(path):
        if path is None:
            return
        try:
            p = Path(path).resolve()
        except Exception:
            return
        if p.is_dir():
            p = p / DEFAULT_CONFIG
        if not p.is_file():
            return
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            candidates.append(p)

    if requested:
        requested_path = Path(requested)
        _add(requested_path)
        for root in _runtime_search_roots():
            _add(root / requested)
            if requested_path.name == DEFAULT_CONFIG:
                _add(root / DEFAULT_CONFIG)
    else:
        for root in _runtime_search_roots():
            _add(root / DEFAULT_CONFIG)

    return candidates


def _resolve_icon_path():
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "icon.ico")
        candidates.append(exe_dir / "assets" / "icon.ico")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass).resolve() / "assets" / "icon.ico")
    else:
        repo_root = Path(__file__).resolve().parent.parent
        candidates.append(repo_root / "assets" / "icon.ico")

    for path in candidates:
        if path.exists():
            return path
    return None


# ---------------------------------------------------------------------------
# Signal config helpers
# ---------------------------------------------------------------------------

class SignalConfigError(Exception):
    pass


def _safe_divider(value):
    try:
        parsed = float(value)
    except Exception:
        return 1.0
    if parsed == 0.0:
        return 1.0
    return parsed


def _read_tab_rows(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        rows.append(text.split("\t"))
    return rows


def _display_name(label, unit):
    clean_label = (label or "").strip() or "Unknown"
    clean_unit = (unit or "").strip()
    if clean_unit and clean_unit != "-":
        return f"{clean_label} [{clean_unit}]"
    return clean_label


def _normalize_signal_key(text):
    if not text:
        return ""
    normalized = []
    for ch in str(text).lower():
        if ch.isalnum():
            normalized.append(ch)
        else:
            normalized.append("_")
    key = "".join(normalized)
    while "__" in key:
        key = key.replace("__", "_")
    return key.strip("_")


def _compact_label_start(text, max_len=8):
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return "Wave"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len]


def load_signal_config(config_path=None):
    candidates = _config_candidates(config_path or "")
    if not candidates:
        searched = "\n  - ".join(
            str(p / DEFAULT_CONFIG) for p in _runtime_search_roots()
        )
        raise SignalConfigError(
            "Config file not found. Looked for:\n  - " + searched
        )
    last_error = None
    raw_cfg = None
    cfg_path = None
    config_dir = None
    params_path = None
    waves_path = None

    for cfg_path in candidates:
        try:
            raw_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            config_dir = cfg_path.parent

            signal_sources = raw_cfg.get("signal_sources", {})
            params_rel = signal_sources.get("params_file")
            waves_rel = signal_sources.get("waves_file")
            if not params_rel or not waves_rel:
                raise SignalConfigError(
                    "missing signal_sources.params_file/waves_file"
                )

            params_path = (config_dir / params_rel).resolve()
            waves_path = (config_dir / waves_rel).resolve()

            if not params_path.exists() or not waves_path.exists():
                for root in _runtime_search_roots():
                    maybe_params = (root / params_rel).resolve()
                    maybe_waves = (root / waves_rel).resolve()
                    if not params_path.exists() and maybe_params.exists():
                        params_path = maybe_params
                    if not waves_path.exists() and maybe_waves.exists():
                        waves_path = maybe_waves

            if not params_path.exists():
                raise SignalConfigError(f"params file not found: {params_path}")
            if not waves_path.exists():
                raise SignalConfigError(f"waves file not found: {waves_path}")
            break
        except Exception as exc:
            last_error = f"{cfg_path}: {exc}"
            raw_cfg = None

    if raw_cfg is None:
        raise SignalConfigError(
            "No valid config found. Last error: " + str(last_error)
        )

    params_rows = _read_tab_rows(params_path)
    waves_rows = _read_tab_rows(waves_path)

    trend_select = raw_cfg["channels"]["trends"]
    wave_select = raw_cfg["channels"]["waves"]

    if len(trend_select) == 0:
        raise SignalConfigError("JSON must declare at least 1 trend row identifier")

    all_trend_defs = []
    for row_id, row in enumerate(params_rows, start=1):
        if len(row) < 7:
            continue
        all_trend_defs.append({
            "row_identifier": row_id,
            "subgroup": int(row[1]),
            "value_index": int(row[2]),
            "divider": _safe_divider(row[3]),
            "label": row[4].strip(),
            "unit": row[5].strip(),
            "title": _display_name(row[4].strip(), row[5].strip()),
        })

    all_wave_defs = []
    for row_id, row in enumerate(waves_rows, start=1):
        if len(row) < 8:
            continue
        all_wave_defs.append({
            "row_identifier": row_id,
            "sr_type": row_id,
            "sample_hz": max(1.0, float(row[1])),
            "divider": _safe_divider(row[3]),
            "label": row[5].strip(),
            "unit": row[6].strip(),
            "title": _display_name(row[5].strip(), row[6].strip()),
        })

    trend_by_row = {item["row_identifier"]: item for item in all_trend_defs}
    wave_by_row = {item["row_identifier"]: item for item in all_wave_defs}

    trend_defs = []
    for item in trend_select:
        row_id = int(item["row_identifier"])
        if row_id not in trend_by_row:
            raise SignalConfigError(f"Trend row_identifier out of range: {row_id}")
        selected = dict(trend_by_row[row_id])
        selected["id"] = f"t_{row_id}"
        trend_defs.append(selected)

    wave_defs = []
    for item in wave_select:
        row_id = int(item["row_identifier"])
        if row_id not in wave_by_row:
            raise SignalConfigError(f"Wave row_identifier out of range: {row_id}")
        selected = dict(wave_by_row[row_id])
        selected["id"] = f"w_{row_id}"
        wave_defs.append(selected)

    ui_cfg = raw_cfg.get("ui", {})
    conn_cfg = ui_cfg.get("connection", {})
    sim_cfg = ui_cfg.get("simulator", {})

    initial_baudrate = int(conn_cfg.get("baudrate", 19200))
    if initial_baudrate not in (19200, 115200):
        initial_baudrate = 19200

    user_role = raw_cfg.get("user_role", "Administrator")
    if user_role not in ("Administrator", "Reviewer", "Recorded"):
        user_role = "Administrator"

    return {
        "path": str(cfg_path),
        "config_dir": str(config_dir),
        "all_trend_defs": all_trend_defs,
        "all_wave_defs": all_wave_defs,
        "trend_defs": trend_defs,
        "wave_defs": wave_defs,
        "initial_duration": max(5, int(ui_cfg.get("duration_sec", 60))),
        "initial_trend_window": max(10.0, float(ui_cfg.get("trend_window_sec", 60))),
        "initial_wave_window": max(10.0, float(ui_cfg.get("wave_window_sec", 10))),
        "initial_baudrate": initial_baudrate,
        "initial_output_directory": str(ui_cfg.get("output_directory", "")).strip(),
        "initial_output_filename": str(ui_cfg.get("output_filename", "")).strip(),
        "initial_review_file": str(ui_cfg.get("review_file", "")).strip(),
        "initial_last_active_drc_file": str(ui_cfg.get("last_active_drc_file", "")).strip(),
        "initial_sim_speed": max(0.05, min(1000.0, float(sim_cfg.get("speed_multiplier", 1.0)))),
        "initial_split_ratio": max(0.1, min(0.9, float(ui_cfg.get("graph_split_ratio", 0.5)))),
        "colors": raw_cfg.get("colors", {}),
        "user_role": user_role,
        "protocol": raw_cfg.get("protocol", {}),
        "notes": raw_cfg.get("notes", {}),
    }
