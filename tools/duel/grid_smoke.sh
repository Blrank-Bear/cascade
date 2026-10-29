#!/usr/bin/env bash
# CPU smoke test of tools/duel/grid.py: 2 arms, 1 pool, 1 round seed, tiny budget.
# Usage: MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tools/duel/grid_smoke.sh [ARMS.json] [HOURS] [N_WINDOWS]
set -euo pipefail
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
W=$ROOT/.claude-work
ARMS=${1:-$W/tmp/arms_smoke.json}; HOURS=${2:-0.0002}; NW=${3:-60}
export NUMBA_CACHE_DIR=$W/cache/numba OMP_NUM_THREADS=8
cd "$ROOT/upstream"
"$W/venv/bin/python" "$ROOT/tools/duel/grid.py" "$ARMS" --chain-toml "$W/configs/chain.local-17m.toml" \
  --work "$W/tmp/grid_smoke" --hours "$HOURS" --device cpu --pools 1 --round-seeds smoke-0 --n-windows "$NW"
