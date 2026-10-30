#!/usr/bin/env bash
# Start the local ops dashboard in WSL (binds 127.0.0.1; open http://localhost:PORT in Windows).
# Usage (from Windows): wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tools/dashboard/run_local.sh [PORT]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PORT=${1:-8791}
PY=${PY:-$ROOT/.claude-work/venv/bin/python}
LOG=$ROOT/.claude-work/session/dashboard_local.log
pkill -f "tools/dashboard/local.py" 2>/dev/null || true
mkdir -p "$ROOT/.claude-work/session"
nohup "$PY" -I "$ROOT/tools/dashboard/local.py" --root "$ROOT" --port "$PORT" >> "$LOG" 2>&1 &
disown
sleep 2
echo "local dashboard: http://localhost:$PORT  (log: $LOG)"
