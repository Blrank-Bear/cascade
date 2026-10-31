"""Compare two cascade-benchmark reports (arm vs reference) the way the v2 bench gate looks at them.

    python compare_bench.py ARM.json REF.json [--json OUT.json]

Per suite: aggregate CRPS / MASE and their ratios (arm / ref, < 1 = arm better), plus per-task
ratio mean and win rate (fraction of tasks with ratio < 1).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

METRIC_KEYS = ("crps", "mase")
ID_SKIP = set(METRIC_KEYS) | {"metrics", "wql", "seconds", "elapsed", "timings"}


def row_id(row: dict) -> str:
    if "full" in row:  # cascade-benchmark rows: "dataset/freq/term"
        return str(row["full"])
    return json.dumps({k: v for k, v in row.items() if k not in ID_SKIP}, sort_keys=True, default=str)


def metric(row: dict, m: str):
    v = row.get(m, row.get(m.upper(), (row.get("metrics") or {}).get(m)))
    return v if isinstance(v, (int, float)) and math.isfinite(v) else None


def compare_suite(a: dict, b: dict) -> dict:
    out = {"suite": a["suite"], "status": [a.get("status"), b.get("status")], "n_series": a.get("n_series"),
           "aggregate": {}, "per_task": {}}
    for m in METRIC_KEYS:
        va, vb = (a.get("metrics") or {}).get(m), (b.get("metrics") or {}).get(m)
        if va is not None and vb:
            out["aggregate"][m] = {"ref": vb, "arm": va, "ratio": va / vb}
    ref_rows = {row_id(r): r for r in b.get("rows", [])}
    for m in METRIC_KEYS:
        ratios = []
        for r in a.get("rows", []):
            rb = ref_rows.get(row_id(r))
            va, vb = metric(r, m), (metric(rb, m) if rb else None)
            if va is not None and vb:
                ratios.append(va / vb)
        if ratios:
            out["per_task"][m] = {"n": len(ratios), "mean_ratio": sum(ratios) / len(ratios),
                                  "win_rate": sum(x < 1 for x in ratios) / len(ratios)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", type=Path)
    ap.add_argument("ref", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()
    A, B = json.loads(a.arm.read_text())["suites"], json.loads(a.ref.read_text())["suites"]
    bmap = {s["suite"]: s for s in B}
    res = [compare_suite(s, bmap[s["suite"]]) for s in A if s["suite"] in bmap]
    for r in res:
        print(f"== {r['suite']} (status {r['status'][0]}/{r['status'][1]}, n={r['n_series']})")
        for m, v in r["aggregate"].items():
            print(f"   aggregate {m}: ref {v['ref']:.4f}  arm {v['arm']:.4f}  ratio {v['ratio']:.4f}")
        for m, v in r["per_task"].items():
            print(f"   per-task {m}: n={v['n']}  mean ratio {v['mean_ratio']:.4f}  win rate {v['win_rate']:.2f}")
    if a.json:
        a.json.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
