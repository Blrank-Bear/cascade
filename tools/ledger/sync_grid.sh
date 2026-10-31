#!/usr/bin/env bash
# Snapshot a GPU grid work dir (logs, scores, summaries, train.json, arm configs + generator copies;
# no checkpoint weights) from the server into .claude-work/grids/<grid>/<UTC timestamp>/.
# Usage: bash tools/ledger/sync_grid.sh GRID_NAME [GRID_NAME ...]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
REMOTE=/root/work/cascade/.claude-work
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
for g in "$@"; do
  dst=$ROOT/.claude-work/grids/$g/$STAMP
  mkdir -p "$dst"
  ssh cascade-gpu "cd $REMOTE && tar -cf - --exclude='*.safetensors' --exclude='__pycache__' --exclude='*.pt' $g \$(ls ${g}*.log 2>/dev/null)" | tar -xf - -C "$dst"
  echo "$g -> $dst ($(du -sh "$dst" | cut -f1))"
done
