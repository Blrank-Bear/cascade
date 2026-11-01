"""Where is the trained model's error mass? Rank eval sources by their share of the log-error.

    python error_sources.py SCORE_JSON [SCORE_JSON ...] [--top 20] [--out R.json]

Reads per-window score files (tools/duel score output: one row per eval channel with mase,
qloss_per_q, abs_target, domain, source, horizon) — typically the `base__*` files of several
grid snapshots. The round metric is sqrt(geomean WQL x geomean MASE), i.e. it is driven by the
SUM of log(MASE) and log(WQL) over windows; a source's share of that sum is how much a perfect
fix of that source could move the score. Reported per source: windows, mean log MASE and WQL,
share of total log-error, share of windows with MASE > 1 (worse than in-sample seasonal naive).
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

FLOOR_MASE, FLOOR_WQL = 1e-9, 1e-12


def window_wql(row: dict) -> float | None:
    q, a = row.get("qloss_per_q") or [], row.get("abs_target") or 0.0
    return 2.0 * sum(q) / (len(q) * a) if q and a > 0 else None


def load_rows(paths: list[Path]):
    for p in paths:
        for r in json.loads(p.read_text())["scores"]:
            yield r


def aggregate(rows) -> tuple[dict, float]:
    by = defaultdict(lambda: {"n": 0, "lm": 0.0, "lw": 0.0, "nw": 0, "bad": 0, "domain": "?", "h": defaultdict(int)})
    total = 0.0
    for r in rows:
        m = r.get("mase")
        w = window_wql(r)
        if m is None:
            continue
        lm = math.log(max(m, FLOOR_MASE))
        s = by[r.get("source", "?")]
        s["n"] += 1
        s["lm"] += lm
        s["bad"] += m > 1.0
        s["domain"] = r.get("domain", "?")
        s["h"][str(r.get("horizon"))] += 1
        if w is not None:
            lw = math.log(max(w, FLOOR_WQL))
            s["lw"] += lw
            s["nw"] += 1
            total += lw
        total += lm
    return by, total


def report(by: dict, total: float, top: int) -> list[dict]:
    rows = []
    for src, s in by.items():
        mass = s["lm"] + s["lw"]
        rows.append({"source": src, "domain": s["domain"], "n": s["n"],
                     "mean_log_mase": s["lm"] / s["n"], "mean_log_wql": s["lw"] / max(1, s["nw"]),
                     "mase_gt1_share": s["bad"] / s["n"], "log_error_mass": mass,
                     "share_of_total": mass / total if total else None})
    rows.sort(key=lambda r: -r["log_error_mass"])
    return rows[:top]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scores", type=Path, nargs="+")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    by, total = aggregate(load_rows(a.scores))
    rows = report(by, total, a.top)
    n = sum(s["n"] for s in by.values())
    print(f"windows {n}, sources {len(by)}, total log-error {total:.1f} (positive = error mass)")
    print(f"{'source':48s} {'domain':12s} {'n':>5s} {'logMASE':>8s} {'logWQL':>8s} {'MASE>1':>7s} {'share':>7s}")
    for r in rows:
        print(f"{r['source'][:48]:48s} {r['domain'][:12]:12s} {r['n']:5d} {r['mean_log_mase']:8.3f} "
              f"{r['mean_log_wql']:8.3f} {r['mase_gt1_share']:7.2f} {r['share_of_total'] * 100:6.1f}%")
    if a.out:
        a.out.write_text(json.dumps({"windows": n, "total": total, "top": rows}, indent=1) + "\n")


if __name__ == "__main__":
    main()
