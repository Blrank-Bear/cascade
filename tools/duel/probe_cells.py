"""Focused (partial) test report: an arm's gain vs base on its TARGET cell (horizon x domain), plus overall.

    python probe_cells.py WORK ARMS_JSON [--base base] [--targets TARGETS_JSON] [--out R.json]

Reads WORK/scores (same windows, same order for every arm; tools/duel/breakdown_scores.paired_rows).
Gain is the mean over windows of -(half log MASE + half log WQL) ratio arm/base, so +0.01 = 1% better.
TARGETS_JSON maps arm -> [[horizon, domain], ...] (domain "*" = all); arms without targets report overall only.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import breakdown_scores as B


def window_gain(ra: dict, rb: dict) -> float | None:
    m = B.log_ratio(ra.get("mase"), rb.get("mase"), B.FLOOR_MASE)
    w = B.log_ratio(B.window_wql(ra), B.window_wql(rb), B.FLOOR_WQL)
    return None if m is None or w is None else -0.5 * (m + w)


def cell_gains(work: Path, arm: str, base: str) -> dict:
    cells = defaultdict(list)
    for ra, rb in B.paired_rows(work, arm, base):
        g = window_gain(ra, rb)
        if g is None:
            continue
        h, d = str(ra.get("horizon")), ra.get("domain") or "?"
        for key in ((h, d), (h, "*"), ("*", d), ("*", "*")):
            cells[key].append(g)
    return {k: (sum(v) / len(v), len(v)) for k, v in cells.items()}


def report(work: Path, arms: list[str], base: str, targets: dict) -> dict:
    out = {}
    for arm in arms:
        cg = cell_gains(work, arm, base)
        overall = cg.get(("*", "*"), (None, 0))
        tg = {f"{h}|{d}": cg.get((str(h), d), (None, 0)) for h, d in targets.get(arm, [])}
        out[arm] = {"overall": overall[0], "n": overall[1], "targets": {k: v[0] for k, v in tg.items()},
                    "horizons": {h: cg[(h, "*")][0] for h in ("64", "256", "720") if (h, "*") in cg}}
        t = " ".join(f"{k}={v[0] * 100:+.2f}%" for k, v in tg.items() if v[0] is not None)
        hz = " ".join(f"h{h}={g * 100:+.2f}%" for h, g in out[arm]["horizons"].items())
        print(f"{arm:14s} overall {overall[0] * 100 if overall[0] is not None else float('nan'):+6.2f}%  {hz}  {t}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("arms", type=Path)
    ap.add_argument("--base", default="base")
    ap.add_argument("--targets", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    arms = [k for k in json.loads(a.arms.read_text()) if k != a.base]
    targets = json.loads(a.targets.read_text()) if a.targets else {}
    res = report(a.work, arms, a.base, targets)
    if a.out:
        a.out.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
