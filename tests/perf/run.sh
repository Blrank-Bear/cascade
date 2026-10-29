#!/usr/bin/env bash
# Usage: MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tests/perf/run.sh [SECONDS] [AS_MB] [GEN_DIR]
# Runs the generator pinned to one core with v2-child thread caps and RLIMIT_AS.
set -euo pipefail
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
SECONDS_RUN=${1:-120}
AS_MB=${2:-2048}
GEN=${3:-$ROOT/generator}
export NUMBA_CACHE_DIR=$ROOT/.claude-work/cache/numba
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 NUMBA_NUM_THREADS=1
unshare -rn taskset -c 0 "$ROOT/.claude-work/venv/bin/python" -I "$ROOT/tests/perf/measure.py" "$GEN" \
  --seconds "$SECONDS_RUN" --as-mb "$AS_MB"
