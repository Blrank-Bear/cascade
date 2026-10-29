#!/usr/bin/env bash
# Usage (from Windows Git Bash):
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tests/golden/run.sh [record|check] [N]
# record: write tests/golden/expected_{natural,late}.json from generator/
# check : regenerate into .claude-work/tmp/ and diff against the expected files
set -euo pipefail
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
PY=$ROOT/.claude-work/venv/bin/python
ACTION=${1:-check}
N=${2:-600}
OUT=$ROOT/tests/golden
[ "$ACTION" = check ] && OUT=$ROOT/.claude-work/tmp/golden && mkdir -p "$OUT"
export NUMBA_CACHE_DIR=$ROOT/.claude-work/cache/numba
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1

for MODE in natural late; do
  # unshare -rn: run with no network access.
  unshare -rn "$PY" -I "$ROOT/tests/golden/harness.py" "$ROOT/generator" \
    --mode "$MODE" --n "$N" --out "$OUT/expected_$MODE.json"
done

if [ "$ACTION" = check ]; then
  ok=0
  for MODE in natural late; do
    if "$PY" -c "import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); \
f=lambda d:{k:(v['sha256'],v['count'],v['shapes']) for k,v in d['seeds'].items()}; sys.exit(f(a)!=f(b) or a['overrides']!=b['overrides'])" \
        "$ROOT/tests/golden/expected_$MODE.json" "$OUT/expected_$MODE.json"; then
      echo "GOLDEN $MODE: OK"
    else
      echo "GOLDEN $MODE: MISMATCH"; ok=1
    fi
  done
  exit $ok
fi
