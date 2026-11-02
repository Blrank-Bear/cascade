"""Champion gate: only arms that reach champion level on the first seed get more seeds.

    python seed_gate.py SUMMARY_JSON ARMS_JSON OUT_ARMS_JSON [--min-gain 0.01] [--log GATE_LOG]

Reads a finished seed's grid summary (summary[arm][cell] with chal_geomean / king_geomean, the
reference arm as "king"), computes each arm's mean gain over cells (1 - arm/base round metric),
and writes OUT_ARMS_JSON with the reference arm plus only the arms whose gain >= --min-gain
(default +1%: roughly what a dethrone needs). Exit code 3 if no arm passes (caller skips the seed).
Every decision is appended to --log as one JSON line.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def arm_gain(cells: dict) -> float | None:
    gains = [1 - c["chal_geomean"] / c["king_geomean"] for k, c in cells.items()
             if not k.startswith("_") and c.get("king_geomean") and c.get("chal_geomean")]
    return sum(gains) / len(gains) if gains else None


def gate(summary: dict, arms: dict, ref: str, min_gain: float) -> tuple[dict, dict]:
    gains = {a: arm_gain(summary.get(a) or {}) for a in arms if a != ref}
    passed = {a: s for a, s in arms.items() if a == ref or (gains.get(a) is not None and gains[a] >= min_gain)}
    return passed, gains


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("summary", type=Path)
    ap.add_argument("arms", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--ref", default="base")
    ap.add_argument("--min-gain", type=float, default=0.01)
    ap.add_argument("--log", type=Path, default=None)
    a = ap.parse_args()
    passed, gains = gate(json.loads(a.summary.read_text()), json.loads(a.arms.read_text()), a.ref, a.min_gain)
    a.out.write_text(json.dumps(passed, indent=1) + "\n")
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": str(a.summary),
           "arms": str(a.arms), "min_gain": a.min_gain, "gains": gains, "passed": [k for k in passed if k != a.ref]}
    if a.log:
        with a.log.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))
    sys.exit(0 if rec["passed"] else 3)


if __name__ == "__main__":
    main()
