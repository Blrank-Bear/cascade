"""Rigorous, feature-by-feature analysis of the experiment ledger.

    python analyze.py [--ledger ledger/experiments.jsonl] [--out ledger/analysis.md]

Only valid records (equal steps, same generator, no failures) and only single-feature arms
(exactly one switch file differs from the reference) are used. Each feature (its exact switch
config) is aggregated across training seeds: per-seed mean gain over all cells, per-horizon and
per-domain effects, mean / sd / t across seeds, sign consistency.

Verdict rules (fixed in advance):
  ADOPT-CANDIDATE  >= MIN_SEEDS seeds, every seed's mean gain > 0, t >= T_MIN,
                   and no horizon whose cross-seed mean is below -HORIZON_FLOOR
  REJECT           >= MIN_SEEDS seeds, mean gain < 0 and (every seed < 0 or t <= -T_MIN)
  INCONCLUSIVE     anything else (more seeds needed, or mixed horizons)
Gain = 1 - arm/base round metric (positive = better than the reference).
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIN_SEEDS, T_MIN, HORIZON_FLOOR = 3, 2.5, 0.005


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.is_file() else []


def feature_key(arm: dict, ref_sw: dict) -> str:
    diff = {k: v for k, v in arm["switches"].items() if ref_sw.get(k) != v}
    return json.dumps(diff, sort_keys=True)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def stats(xs: list[float]) -> dict:
    n = len(xs)
    m = mean(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else None
    t = m / (sd / math.sqrt(n)) if sd else None
    return {"n": n, "mean": m, "sd": sd, "t": t, "min": min(xs) if xs else None, "max": max(xs) if xs else None,
            "all_pos": n > 0 and all(x > 0 for x in xs), "all_neg": n > 0 and all(x < 0 for x in xs)}


def seed_summary(arm: dict) -> dict:
    cells = arm.get("cells", {})
    horizons = defaultdict(list)
    for c in cells.values():
        for h, v in (c.get("per_horizon") or {}).items():
            horizons[h].append(v)
    return {"gain": mean([c["gain"] for c in cells.values()]),
            "wins": sum(bool(c.get("win")) for c in cells.values()), "cells": len(cells),
            "horizon": {h: mean(v) for h, v in horizons.items()},
            "domain": {d: r.get("log_mase") for d, r in (arm.get("breakdown", {}).get("domain") or {}).items()}}


def collect(records: list[dict]):
    features, excluded = defaultdict(list), []
    for r in records:
        if not r.get("valid"):
            excluded.append((r["id"], "invalid: " + ",".join(r.get("invalid_reasons", []))))
            continue
        ref_sw = r["arms"][r["reference"]]["switches"]
        for name in r["judged_arms"]:
            arm = r["arms"][name]
            if not arm.get("single_feature"):
                excluded.append((f"{r['id']}:{name}", f"multi-feature ({arm.get('n_features_vs_ref')} switches differ)"))
                continue
            features[feature_key(arm, ref_sw)].append({"record": r["id"], "arm": name, "seed": r["budget"]["train_seed"],
                                                       "steps": r["steps"], **seed_summary(arm)})
    return features, excluded


def verdict(s: dict, horizon_means: dict) -> str:
    worst_h = min(horizon_means.values()) if horizon_means else 0.0
    if s["n"] >= MIN_SEEDS and s["all_pos"] and (s["t"] or 0) >= T_MIN and worst_h >= -HORIZON_FLOOR:
        return "ADOPT-CANDIDATE"
    if s["n"] >= MIN_SEEDS and s["mean"] is not None and s["mean"] < 0 and (s["all_neg"] or (s["t"] or 0) <= -T_MIN):
        return "REJECT"
    return "INCONCLUSIVE"


def analyse(features: dict) -> list[dict]:
    out = []
    for key, runs in features.items():
        by_seed = {}
        for r in runs:  # one result per seed (latest record wins)
            by_seed[r["seed"]] = r
        runs = [by_seed[s] for s in sorted(by_seed)]
        s = stats([r["gain"] for r in runs])
        hs = sorted({h for r in runs for h in r["horizon"]}, key=lambda h: int(h))
        horizon_means = {h: mean([r["horizon"].get(h) for r in runs]) for h in hs}
        domains = sorted({d for r in runs for d in r["domain"]})
        domain_means = {d: mean([r["domain"].get(d) for r in runs]) for d in domains}
        out.append({"feature": key, "arm_names": sorted({r["arm"] for r in runs}), "seeds": [r["seed"] for r in runs],
                    "per_seed_gain": [r["gain"] for r in runs], "per_seed_wins": [f"{r['wins']}/{r['cells']}" for r in runs],
                    "stats": s, "horizon_means": horizon_means, "domain_log_mase": domain_means,
                    "verdict": verdict(s, horizon_means)})
    return sorted(out, key=lambda f: -(f["stats"]["mean"] or -9))


def pct(x):
    return "—" if x is None else f"{x * 100:+.2f}%"


def render(results: list[dict], excluded: list) -> str:
    lines = ["# Experiment ledger analysis (feature by feature)", "",
             f"Rules: ADOPT-CANDIDATE needs ≥{MIN_SEEDS} seeds, every seed > 0, t ≥ {T_MIN}, no horizon below −{HORIZON_FLOOR*100:.1f}%. "
             "Only valid records and single-feature arms are used.", "",
             "| Feature (switch vs reference) | Arm | Seeds | Per-seed gain | Mean | sd | t | Horizons (64/256/720) | Verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    for f in results:
        s = f["stats"]
        hz = " / ".join(pct(f["horizon_means"].get(h)) for h in ("64", "256", "720"))
        lines.append(f"| `{f['feature']}` | {', '.join(f['arm_names'])} | {f['seeds']} | {', '.join(pct(g) for g in f['per_seed_gain'])} | "
                     f"{pct(s['mean'])} | {pct(s['sd'])} | {'—' if s['t'] is None else f'{s[chr(116)]:.2f}'} | {hz} | **{f['verdict']}** |")
    lines += ["", "## Per-domain effect (mean log MASE arm/reference across seeds; negative = better)", ""]
    for f in results:
        dm = ", ".join(f"{d} {v:+.3f}" for d, v in sorted(f["domain_log_mase"].items(), key=lambda kv: kv[1]) if v is not None)
        lines.append(f"- **{', '.join(f['arm_names'])}**: {dm}")
    lines += ["", "## Excluded", ""] + [f"- `{i}`: {why}" for i, why in excluded]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=Path, default=ROOT / "ledger" / "experiments.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "ledger" / "analysis.md")
    a = ap.parse_args()
    features, excluded = collect(load(a.ledger))
    results = analyse(features)
    text = render(results, excluded)
    a.out.write_text(text)
    (a.out.with_suffix(".json")).write_text(json.dumps({"results": results, "excluded": excluded}, indent=1) + "\n")
    print(text)


if __name__ == "__main__":
    main()
