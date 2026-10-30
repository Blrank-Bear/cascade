#!/usr/bin/env bash
# Equivalence + speed check for the screening MoE patch: train STEPS steps with duel.py
# twice (noise floor) and with duel_fast.py once, same seed; compare final weights.
# Usage (GPU box): bash tools/duel/fast_moe_check.sh GEN_DIR CHAIN_TOML [STEPS]
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
GEN=$1; CFG=$2; STEPS=${3:-3}
OUT=$R/.claude-work/tmp/fast_moe_check
HOURS=$(python3 -c "print($STEPS * 3.0 / 23841 + 1e-9)")
export NUMBA_CACHE_DIR=$R/.claude-work/cache/numba PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$R/upstream"
PY=.venv/bin/python
rm -rf "$OUT"; mkdir -p "$OUT"
for run in orig_a orig_b fast; do
  script=$R/tools/duel/duel.py; [ "$run" = fast ] && script=$R/tools/duel/duel_fast.py
  s=$(date +%s)
  $PY "$script" train "$GEN" --chain-toml "$CFG" --out "$OUT/$run" --seed 0 --device cuda --hours "$HOURS" > "$OUT/$run.log" 2>&1
  echo "$run wall $(( $(date +%s) - s )) s"
done
$PY - "$OUT" <<'EOF'
import sys
from pathlib import Path
from safetensors.torch import load_file
out = Path(sys.argv[1])
w = {k: load_file(str(out / k / "weights.safetensors")) for k in ("orig_a", "orig_b", "fast")}
def maxdiff(a, b):
    return max(float((w[a][n].float() - w[b][n].float()).abs().max()) for n in w[a])
def bitwise(a, b):
    return all(bool((w[a][n] == w[b][n]).all()) for n in w[a])
print(f"orig_a vs orig_b: max|d| {maxdiff('orig_a', 'orig_b'):.3e} bitwise {bitwise('orig_a', 'orig_b')}")
print(f"orig_a vs fast  : max|d| {maxdiff('orig_a', 'fast'):.3e} bitwise {bitwise('orig_a', 'fast')}")
EOF
