#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"
DRC="$HOME/Documents/GitLab/algorithms-tools/iCollect/Example.drc"
SIM_PORT="/dev/ttyS4"
GUI_PORT="/dev/ttyUSB0"  # Set this to your patient monitor USB-serial device

show_help() {
  cat <<'EOF'
Usage: ./run_pycollect.sh <option>
Options:
  1  Run simulator only
  2  Run Qt GUI collector only
  3  Run simulator + Qt GUI together
  4  Convert DRC files in current folder to CSV
  5  Run Qt GUI collector from real monitor
  help  Show this message
EOF
}

case "${1:-help}" in
  1)
    echo "[1] Simulator only"
    echo "Command: $PY drc_monitor_simulator.py --drc \"$DRC\" --port $SIM_PORT --wait-command --max-records 3600 --interval 0.02"
    exec "$PY" "$ROOT/drc_monitor_simulator.py" --drc "$DRC" --port "$SIM_PORT" --wait-command --max-records 3600 --interval 0.02
    ;;
  2)
    echo "[2] Qt GUI collector only"
    echo "Command: $PY pycollect.py --qt-gui $GUI_PORT --output record.drc --simulation-mode"
    exec "$PY" "$ROOT/pycollect.py" --qt-gui "$GUI_PORT" --output record.drc --simulation-mode
    ;;
  3)
    echo "[3] Simulator + Qt GUI (auto-stop simulator after GUI exits)"
    "$PY" "$ROOT/drc_monitor_simulator.py" --drc "$DRC" --port "$SIM_PORT" --wait-command --max-records 3600 --interval 0.02 &
    SIM_PID=$!
    trap 'kill "$SIM_PID" 2>/dev/null || true' EXIT
    "$PY" "$ROOT/pycollect.py" --qt-gui "$GUI_PORT" --output record.drc --simulation-mode
    kill "$SIM_PID" 2>/dev/null || true
    ;;
  4)
    echo "[4] Convert DRC files in current folder to CSV"
    echo "Command: $PY drc_2_csv.py "$ROOT" "$ROOT/params5.txt" "$ROOT/waves5.txt""
    exec "$PY" "$ROOT/drc_2_csv.py" "$ROOT" "$ROOT/params5.txt" "$ROOT/waves5.txt"
    ;;
  5)
    echo "[5] Qt GUI collector from real monitor"
    echo "Command: $PY pycollect.py --qt-gui $GUI_PORT --output record.drc"
    exec "$PY" "$ROOT/pycollect.py" --qt-gui "$GUI_PORT" --output record.drc
    ;;
  help|*)
    show_help
    ;;
esac
