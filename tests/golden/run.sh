#!/usr/bin/env bash
# Usage (from Windows Git Bash):
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tests/golden/run.sh [record|check] [N] [SUITES]
# SUITES (default "inner v2"):
#   inner: the pre-v2 king stream (_V2PackParent) -> expected_{natural,late}.json
#   v2   : the packed v2 records (Generator)      -> expected_v2_{natural,late}.json
# record: write the expected files; check: regenerate into .claude-work/tmp/golden and compare.
set -euo pipefail
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
PY=$ROOT/.claude-work/venv/bin/python
ACTION=${1:-check}
N_ARG=${2:-default}
SUITES=${3:-inner v2}
EXP=$ROOT/tests/golden
OUT=$EXP
[ "$ACTION" = check ] && OUT=$ROOT/.claude-work/tmp/golden && mkdir -p "$OUT"
export NUMBA_CACHE_DIR=$ROOT/.claude-work/cache/numba
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1

suite_class() { [ "$1" = inner ] && echo _V2PackParent || echo Generator; }
suite_file() { [ "$1" = inner ] && echo "expected_$2.json" || echo "expected_v2_$2.json"; }
# Default record counts the expected files were made with: inner 600 rows, v2 200 records.
suite_n() { [ "$N_ARG" != default ] && echo "$N_ARG" || { [ "$1" = inner ] && echo 600 || echo 200; }; }

status=0
for SUITE in $SUITES; do
  for MODE in natural late; do
    FILE=$(suite_file "$SUITE" "$MODE")
    # unshare -rn: run with no network access.
    unshare -rn "$PY" -I "$ROOT/tests/golden/harness.py" "$ROOT/generator" \
      --cls "$(suite_class "$SUITE")" --mode "$MODE" --n "$(suite_n "$SUITE")" --out "$OUT/$FILE" > /dev/null
    [ "$ACTION" = check ] || continue
    if "$PY" -c "import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); \
f=lambda d:{k:(v['sha256'],v['count'],v['shapes']) for k,v in d['seeds'].items()}; sys.exit(f(a)!=f(b) or a['overrides']!=b['overrides'])" \
        "$EXP/$FILE" "$OUT/$FILE"; then
      echo "GOLDEN $SUITE $MODE: OK"
    else
      echo "GOLDEN $SUITE $MODE: MISMATCH"; status=1
    fi
  done
done
exit $status
