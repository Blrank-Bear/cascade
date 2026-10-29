"""Golden-output harness: digest a generator's first N yields per seed.

Run before and after every refactor step; the digests must be byte-identical.

    python harness.py GEN_DIR --out digests.json [--n 600] [--seeds 0,1,...] [--mode natural|late]

Mode "late" shrinks the module's stream-budget constants so the late-stream
layers (C91/C124B2 holds, YZ/YC, YQH, C215-LP) fire within a short run.
Those constant names must therefore survive refactoring unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

DEFAULT_SEEDS = (0, 1, 12345, 2**32 + 7, 2**62 + 99991, 2**63 - 1)

# Module constant -> value used in "late" mode.
LATE_OVERRIDES = {
    "_C91_CHILD_BUDGET": 200_000,
    "_YZ_CHILD_BUDGET": 200_000,
    "_C215LP_STREAM_POINTS": 1_000_000,
}


def load_module(gen_dir: Path):
    sys.path.insert(0, str(gen_dir))
    spec = importlib.util.spec_from_file_location("generator", gen_dir / "generator.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generator"] = module
    spec.loader.exec_module(module)
    return module


def apply_overrides(module, overrides: dict) -> dict:
    applied = {}
    for name, value in overrides.items():
        if hasattr(module, name):
            setattr(module, name, value)
            applied[name] = value
    return applied


def record_values(item):
    return item["values"] if isinstance(item, dict) else item


def update_digest(h, arr: np.ndarray) -> None:
    arr = np.ascontiguousarray(arr)
    h.update(f"{arr.dtype.str}|{arr.shape}|".encode())
    h.update(arr.tobytes())


def digest_seed(module, gen_dir: Path, seed: int, n: int) -> dict:
    gen = module.Generator(str(gen_dir), seed=seed)
    h = hashlib.sha256()
    shapes: dict[str, int] = {}
    count = 0
    t0 = time.perf_counter()
    for item in gen.generate(n):
        arr = np.asarray(record_values(item))
        update_digest(h, arr)
        key = "x".join(map(str, arr.shape))
        shapes[key] = shapes.get(key, 0) + 1
        count += 1
        if count >= n:
            break
    return {"sha256": h.hexdigest(), "count": count, "shapes": shapes,
            "seconds": round(time.perf_counter() - t0, 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gen_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)))
    ap.add_argument("--mode", choices=("natural", "late"), default="natural")
    args = ap.parse_args()

    gen_dir = args.gen_dir.resolve()
    module = load_module(gen_dir)
    applied = apply_overrides(module, LATE_OVERRIDES) if args.mode == "late" else {}
    seeds = [int(s) for s in args.seeds.split(",")]
    result = {"mode": args.mode, "n": args.n, "overrides": applied, "seeds": {}}
    for seed in seeds:
        result["seeds"][str(seed)] = digest_seed(module, gen_dir, seed, args.n)
        print(seed, result["seeds"][str(seed)], flush=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
