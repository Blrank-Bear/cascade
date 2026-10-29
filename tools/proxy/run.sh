#!/usr/bin/env bash
# CPU coverage proxy: sample a generator, then compare against the newest pool snapshots.
# Usage (from Windows Git Bash):
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tools/proxy/run.sh TAG [GEN_DIR] [MODE] [RECORDS]
# Output: .claude-work/tmp/proxy/TAG.{npz,json}
set -euo pipefail
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
PY=$ROOT/.claude-work/venv/bin/python
TAG=${1:?tag}
GEN=${2:-$ROOT/generator}
MODE=${3:-natural}
RECORDS=${4:-400}
OUT=$ROOT/.claude-work/tmp/proxy
mkdir -p "$OUT"
export NUMBA_CACHE_DIR=$ROOT/.claude-work/cache/numba
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1
POOLS=()
for d in $(ls -d "$ROOT"/.claude-work/data/pools/*-block-* | sort | tail -3); do POOLS+=(--pool-dir "$d"); done
# unshare -rn: the generator runs with no network access.
unshare -rn "$PY" -I "$ROOT/tools/proxy/sample.py" "$GEN" --out "$OUT/$TAG.npz" --mode "$MODE" --records "$RECORDS"
"$PY" -I "$ROOT/tools/proxy/compare.py" "$OUT/$TAG.npz" "${POOLS[@]}" --out "$OUT/$TAG.json"
