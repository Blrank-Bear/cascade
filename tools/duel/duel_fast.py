"""duel.py with the screening-only MoE speed patch (tools/duel/fast_moe.py) applied.

Same arguments as duel.py. Use for local screening only; results should match
duel.py (see tools/duel/fast_moe_check.sh), just faster.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fast_moe  # noqa: E402

fast_moe.apply()
runpy.run_path(str(HERE / "duel.py"), run_name="__main__")
