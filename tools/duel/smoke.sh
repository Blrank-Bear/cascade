#!/usr/bin/env bash
# CPU smoke test of tools/duel: two generators, tiny budget, a few hundred windows.
# Usage: MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/CODE/Bittensor/cascade/cascade/tools/duel/smoke.sh KING_GEN CHAL_GEN [HOURS] [N_WINDOWS]
set -euo pipefail
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
W=$ROOT/.claude-work
PY=$W/venv/bin/python
KING=$1; CHAL=$2; HOURS=${3:-0.0005}; NW=${4:-300}
CFG=$W/configs/chain.local-17m.toml
POOL=$(ls -d $W/data/pools/*-block-* | tail -1)
OUT=$W/tmp/duel_smoke; mkdir -p "$OUT"
export NUMBA_CACHE_DIR=$W/cache/numba OMP_NUM_THREADS=8
cd "$ROOT/upstream"
for side in king chal; do
  GEN=$KING; [ $side = chal ] && GEN=$CHAL
  "$PY" "$ROOT/tools/duel/duel.py" train "$GEN" --chain-toml "$CFG" --out "$OUT/ckpt_$side" --hours "$HOURS" --seed 0 > "$OUT/train_$side.json"
  "$PY" "$ROOT/tools/duel/duel.py" score "$OUT/ckpt_$side" --chain-toml "$CFG" --pool-dir "$POOL" --n-windows "$NW" --out "$OUT/scores_$side.json"
done
"$PY" "$ROOT/tools/duel/duel.py" judge "$OUT/scores_king.json" "$OUT/scores_chal.json" --chain-toml "$CFG" --margin 0.01
