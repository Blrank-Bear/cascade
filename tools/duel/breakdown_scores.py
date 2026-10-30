"""Where does an arm gain or lose vs base? Per-domain / horizon / source breakdown of grid scores.

Reads WORK/scores/<arm>__<pool>__<seed>.json and the matching base files (same windows,
same order) and reports the mean log ratio arm/base of per-window MASE and WQL
(negative = arm better), grouped by domain, horizon and the most frequent sources.

    python breakdown_scores.py WORK ARM [--base base] [--top-sources 12]
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


def log_ratio(a: float | None, b: float | None, floor: float) -> float | None:
    if a is None or b is None:
        return None
    return math.log(max(a, floor)) - math.log(max(b, floor))


def paired_rows(work: Path, arm: str, base: str):
    for f in sorted((work / "scores").glob(f"{arm}__*.json")):
        bf = f.with_name(f.name.replace(f"{arm}__", f"{base}__", 1))
        if not bf.is_file():
            continue
        a, b = json.loads(f.read_text())["scores"], json.loads(bf.read_text())["scores"]
        for ra, rb in zip(a, b):
            if ra.get("series_id") == rb.get("series_id") and ra.get("channel") == rb.get("channel"):
                yield ra, rb


def summarise(groups: dict) -> dict:
    out = {}
    for key, vals in groups.items():
        m = [v[0] for v in vals if v[0] is not None]
        w = [v[1] for v in vals if v[1] is not None]
        out[key] = {"n": len(vals), "log_mase": round(sum(m) / len(m), 4) if m else None,
                    "log_wql": round(sum(w) / len(w), 4) if w else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("arm")
    ap.add_argument("--base", default="base")
    ap.add_argument("--top-sources", type=int, default=12)
    args = ap.parse_args()
    by = {"domain": defaultdict(list), "horizon": defaultdict(list), "source": defaultdict(list)}
    for ra, rb in paired_rows(args.work, args.arm, args.base):
        v = (log_ratio(ra.get("mase"), rb.get("mase"), FLOOR_MASE),
             log_ratio(window_wql(ra), window_wql(rb), FLOOR_WQL))
        by["domain"][ra.get("domain", "?")].append(v)
        by["horizon"][str(ra.get("horizon", "?"))].append(v)
        by["source"][ra.get("source", "?")].append(v)
    report = {k: summarise(g) for k, g in by.items()}
    top = sorted(report["source"].items(), key=lambda kv: -kv[1]["n"])[:args.top_sources]
    report["source"] = dict(top)
    for section, rows in report.items():
        print(f"== {section}  (log arm/base; negative = {args.arm} better)")
        for k, r in sorted(rows.items(), key=lambda kv: kv[1]["log_mase"] or 0):
            print(f"  {k:48s} n={r['n']:5d}  mase {r['log_mase']:+.4f}  wql {r['log_wql']:+.4f}")


if __name__ == "__main__":
    main()
