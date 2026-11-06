#!/usr/bin/env bash
# Pre-submission checks for one or more profiles. Never submits, funds or touches a wallet.
# Usage (WSL): bash tools/submit/preflight.sh [PROFILE ...]   (default: base j30)
#   LIVE=1 also runs `cascade verify --live` (needs the deployed v2 contract to be discoverable).
# Report: submission/PREFLIGHT.json (+ per-check logs in submission/<profile>/logs/).
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY=$ROOT/.claude-work/venv/bin/python
CASCADE=$ROOT/.claude-work/venv/bin/cascade
KING=${KING:-$ROOT/reference/kings/2026-10-22-04e226724e3b}  # env override: dedup against another archived king
PROFILES=${*:-base j30}
export NUMBA_CACHE_DIR=$ROOT/.claude-work/cache/numba OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
REPORT=$ROOT/submission/PREFLIGHT.json
mkdir -p "$ROOT/submission"
echo "{" > "$REPORT.tmp"

run_check() {  # name, logfile, command...
  local name=$1 log=$2; shift 2
  local t0=$SECONDS
  "$@" > "$log" 2>&1
  local rc=$?
  printf '  %-26s rc=%-3s %4ss  %s\n' "$name" "$rc" "$((SECONDS - t0))" "$log" >&2
  printf '   "%s": {"rc": %s, "seconds": %s, "log": "%s"},\n' "$name" "$rc" "$((SECONDS - t0))" "$log" >> "$REPORT.tmp"
  return $rc
}

cd "$ROOT/upstream"
for P in $PROFILES; do
  echo "== $P" >&2
  "$PY" "$ROOT/tools/submit/build_package.py" "$P" > /dev/null || { echo "build failed: $P" >&2; exit 2; }
  PKG=$ROOT/submission/$P/generator
  LOGS=$ROOT/submission/$P/logs; mkdir -p "$LOGS"
  echo "  \"$P\": {" >> "$REPORT.tmp"
  # Primary: the v2 contract itself ([training] := upstream [v2.training], unchanged).
  # The plain offline verify below also applies pre-v2 rules, which reject the v2 `groups`
  # field by design, so its failure on corpus_check_failed/groups is expected.
  "$PY" "$ROOT/tools/duel/make_v2_cfg.py" chain.toml "$ROOT/.claude-work/configs/chain.v2-verify.toml" \
      --set 'corpus_mode="shards"' > /dev/null
  run_check verify_v2_contract  "$LOGS/verify_v2.json"       "$CASCADE" verify "$PKG" --chain-toml "$ROOT/.claude-work/configs/chain.v2-verify.toml" --json
  run_check verify_offline      "$LOGS/verify_offline.json"  "$CASCADE" verify "$PKG" --json
  run_check verify_strict_guard "$LOGS/verify_testnet.json"  "$CASCADE" verify "$PKG" --chain-toml chain.testnet.toml --json
  run_check dedup_vs_king       "$LOGS/dedup.json"           "$PY" "$ROOT/tools/submit/dedup_check.py" "$PKG" "$KING"
  if [ "${LIVE:-0}" = 1 ]; then
    run_check verify_live       "$LOGS/verify_live.json"     "$CASCADE" verify "$PKG" --live --json
  fi
  printf '   "manifest": %s\n  },\n' "$(cat "$ROOT/submission/$P/MANIFEST.json")" >> "$REPORT.tmp"
done
echo '  "_done": true' >> "$REPORT.tmp"; echo "}" >> "$REPORT.tmp"
mv "$REPORT.tmp" "$REPORT"
echo "report: $REPORT" >&2
