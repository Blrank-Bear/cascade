"""Validate generator records with cascade's own SeriesValidator under the v2 Lane A policy.

    python validate.py GEN_DIR [--n 300] [--seeds 0,2**62+5]

Checks every record (32 channels, length, finite, float32-safe, canonical groups),
determinism (two draws per seed), exact-duplicate fraction and max |corr| between channels.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from cascade.interface.generator import SeriesValidator, element_dedup_key

V2_POLICY = dict(min_length=64, max_length=32768, min_channels=32, max_channels=32,
                 max_abs=float(np.finfo(np.float32).max), accepted_fields=("groups",))


def load_generator_module(gen_dir: Path):
    sys.path.insert(0, str(gen_dir))
    spec = importlib.util.spec_from_file_location("cascade_submitted_generator", gen_dir / "generator.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cascade_submitted_generator"] = module
    spec.loader.exec_module(module)
    return module


def max_abs_corr(values: np.ndarray) -> float:
    x = values.astype(np.float64)
    sd = x.std(axis=1)
    live = sd > 1e-12
    if live.sum() < 2:
        return 0.0
    z = (x[live] - x[live].mean(axis=1, keepdims=True)) / sd[live, None]
    c = (z @ z.T) / z.shape[1]
    np.fill_diagonal(c, 0.0)
    return float(np.abs(c).max())


def draw(module, gen_dir: Path, seed: int, n: int) -> dict:
    gen = module.Generator(str(gen_dir), seed=seed)
    validator = SeriesValidator(**V2_POLICY)
    h = hashlib.sha256()
    keys = set()
    dup = 0
    group_counts = []
    corr_max = 0.0
    corr_high = 0
    count = 0
    for i, item in enumerate(gen.generate(n)):
        element = validator.process(item, i)
        key = element_dedup_key(element)
        dup += key in keys
        keys.add(key)
        h.update(key)
        group_counts.append(int(np.asarray(item["groups"]).max()) + 1)
        c = max_abs_corr(np.asarray(item["values"]))
        corr_max = max(corr_max, c)
        corr_high += c >= 0.999
        count += 1
    return {"count": count, "sha256": h.hexdigest(), "dup_fraction": dup / max(count, 1),
            "groups_per_record_mean": round(float(np.mean(group_counts)), 2),
            "groups_per_record_min": int(np.min(group_counts)),
            "max_abs_channel_corr": round(corr_max, 6), "records_with_corr_ge_0.999": int(corr_high)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gen_dir", type=Path)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seeds", default=f"0,{2**62 + 5}")
    args = ap.parse_args()
    gen_dir = args.gen_dir.resolve()
    module = load_generator_module(gen_dir)
    report = {}
    for seed in (int(s) for s in args.seeds.split(",")):
        first = draw(module, gen_dir, seed, args.n)
        second = draw(module, gen_dir, seed, args.n)
        first["deterministic"] = first["sha256"] == second["sha256"]
        report[str(seed)] = first
    report["ok"] = all(r["deterministic"] and r["count"] == args.n for r in report.values() if isinstance(r, dict))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
