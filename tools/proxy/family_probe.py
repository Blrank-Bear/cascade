"""Per-family coverage probe: features of one family registry vs. the pool.

    python family_probe.py GEN_DIR --pool-dir POOL [...] [--registry _V2POOL_FAMILIES]
                           [--n 400] [--seed 0] [--out REPORT.json]

Calls each family function `fn(rng, 4096, periods)` from the registry directly
(no king stream), tail-crops to pool lengths and reports, per family, the KS
statistic of every feature against the pool plus the family's mean KS.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import crop_tail, ks_statistic, load_pool  # noqa: E402
from features import FEATURE_NAMES, series_features  # noqa: E402
from sample import load_harness  # noqa: E402


def family_series(module, fn, n: int, seed: int) -> list[np.ndarray]:
    out = []
    for i in range(n):
        rng = np.random.default_rng([seed, i, 0xFA])
        out.append(np.asarray(fn(rng, module._V2_LENGTH, module._v2mix_pick_periods(rng)), dtype=np.float64))
    return out


def family_features(series, pool_lengths, rng) -> np.ndarray:
    lengths = rng.choice(pool_lengths, size=len(series))
    rows = (series_features(crop_tail(x, k)) for x, k in zip(series, lengths))
    return np.asarray([f for f in rows if f is not None])


def family_report(pool: np.ndarray, feats: np.ndarray, n: int) -> dict:
    ks = {name: round(ks_statistic(pool[:, j], feats[:, j]), 3) for j, name in enumerate(FEATURE_NAMES)}
    medians = {name: round(float(np.median(feats[:, j])), 3) for j, name in enumerate(FEATURE_NAMES)}
    return {"usable": f"{len(feats)}/{n}", "mean_ks": round(float(np.mean(list(ks.values()))), 4),
            "ks": dict(sorted(ks.items(), key=lambda kv: -kv[1])), "median": medians}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gen_dir", type=Path)
    ap.add_argument("--pool-dir", type=Path, action="append", required=True)
    ap.add_argument("--registry", default="_V2POOL_FAMILIES")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    module = load_harness().load_module(args.gen_dir.resolve())
    pool, _, lengths = load_pool(args.pool_dir)
    pool_median = {name: round(float(np.median(pool[:, j])), 3) for j, name in enumerate(FEATURE_NAMES)}
    rng = np.random.default_rng(args.seed)
    report = {"registry": args.registry, "pool_median": pool_median, "families": {}}
    for name, fn in getattr(module, args.registry).items():
        feats = family_features(family_series(module, fn, args.n, args.seed), lengths, rng)
        report["families"][name] = family_report(pool, feats, args.n)
    text = json.dumps(report, indent=1)
    if args.out:
        args.out.write_text(text + "\n")
    for name, r in report["families"].items():
        print(name, r["usable"], r["mean_ks"], list(r["ks"].items())[:5])


if __name__ == "__main__":
    main()
