#!/usr/bin/env bash
# Start (or restart) the ops dashboard in tmux session "dash" on the GPU box.
# Usage: bash tools/dashboard/run.sh [PORT]   (default 1122; Clore forwards it publicly)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PORT=${1:-1122}
PY=${PY:-$ROOT/upstream/.venv/bin/python}
tmux kill-session -t dash 2>/dev/null || true
tmux new -d -s dash "$PY $ROOT/tools/dashboard/serve.py --root $ROOT --port $PORT 2>&1 | tee -a $ROOT/.claude-work/session/dashboard.log"
sleep 2
echo "dashboard on port $PORT; token: $ROOT/.claude-work/session/dashboard_token"
