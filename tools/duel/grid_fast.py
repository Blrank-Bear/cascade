"""grid_logged.py, but every duel step runs through duel_fast.py (MoE speed patch).

Same arguments as grid.py. Screening only; see tools/duel/fast_moe.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import grid  # noqa: E402
import grid_logged  # noqa: E402

grid.DUEL = HERE / "duel_fast.py"

if __name__ == "__main__":
    grid_logged.main()
