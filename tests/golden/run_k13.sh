#!/usr/bin/env bash
# Golden digests of the k13 foundation (generator/): natural and late modes (see harness_k13.py).
# Usage: MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tests/golden/run_k13.sh [record|check] [GEN_DIR]
set -euo pipefail
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
PY=$ROOT/.claude-work/venv/bin/python
ACTION=${1:-check}
GEN=${2:-$ROOT/generator}
EXP=$ROOT/tests/golden/k13
OUT=$EXP
mkdir -p "$EXP"
[ "$ACTION" = check ] && OUT=$ROOT/.claude-work/tmp/golden_k13 && mkdir -p "$OUT"
export NUMBA_CACHE_DIR=$ROOT/.claude-work/cache/numba
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1
status=0
for MODE in natural late; do
  FILE=expected_$MODE.json
  # unshare -rn: run with no network access.
  unshare -rn "$PY" -I "$ROOT/tests/golden/harness_k13.py" "$GEN" --mode "$MODE" --out "$OUT/$FILE" > /dev/null
  [ "$ACTION" = check ] || { echo "RECORDED $MODE"; continue; }
  if "$PY" -c "import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); \
f=lambda d:{k:(v['sha256'],v['count'],v['shapes']) for k,v in d['seeds'].items()}; sys.exit(f(a)!=f(b) or a['overrides']!=b['overrides'])" \
      "$EXP/$FILE" "$OUT/$FILE"; then echo "GOLDEN k13 $MODE: OK"; else echo "GOLDEN k13 $MODE: MISMATCH"; status=1; fi
done
exit $status
