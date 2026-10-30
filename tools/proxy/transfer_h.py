"""transfer.py at another eval horizon / context length (h=256 or 720 windows).

transfer.py reads HORIZON and CTX at call time, so this wrapper sets them and runs it
unchanged. All other arguments are transfer.py's.

    python transfer_h.py --horizon 256 --ctx 1024 SAMPLE.npz [...] --chain-toml CFG --pool-dir POOL [...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "duel"))
import transfer  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--horizon", type=int, required=True)
    ap.add_argument("--ctx", type=int, required=True)
    known, rest = ap.parse_known_args()
    transfer.HORIZON, transfer.CTX = known.horizon, known.ctx
    sys.argv = [sys.argv[0], *rest]
    transfer.main()


if __name__ == "__main__":
    main()
