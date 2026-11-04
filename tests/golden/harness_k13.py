"""Golden harness for the reign-13 foundation (generator/): harness.py plus k13 modes.

    python harness_k13.py GEN_DIR --out digests.json --mode natural|late [--take 40] [--seeds ...]

The k13 K0 layers recompute the stream budgets from n inside generate(), and n also caps the parent
record count, so n and the number of digested yields are separate here:
  natural: n = 10_000_000 (budget-gated layers closed early in the stream, as in a real child), take 40.
  late:    n = 2000 (budget-gated layers open after a few records), _LCP_K0 = 40, take 60, so every
           _LCP_SWITCH hook and the late record path run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

MODES = {"natural": {"n": 10_000_000, "take": 40, "overrides": {}},
         "late": {"n": 2000, "take": 60, "overrides": {"_LCP_K0": 40}}}


def digest_take(module, gen_dir: Path, seed: int, n: int, take: int) -> dict:
    gen = module.Generator(str(gen_dir), seed=seed)
    h = hashlib.sha256()
    shapes: dict[str, int] = {}
    count = 0
    t0 = time.perf_counter()
    it = gen.generate(n)
    try:
        for item in it:
            arrays = harness.record_arrays(item)
            for arr in arrays:
                harness.update_digest(h, arr)
            key = "x".join(map(str, arrays[-1].shape))
            shapes[key] = shapes.get(key, 0) + 1
            count += 1
            if count >= take:
                break
    finally:
        it.close()
    return {"sha256": h.hexdigest(), "count": count, "shapes": shapes,
            "seconds": round(time.perf_counter() - t0, 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gen_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=sorted(MODES), default="natural")
    ap.add_argument("--seeds", default="0,1,12345,9223372036854775807")
    a = ap.parse_args()
    m = MODES[a.mode]
    gen_dir = a.gen_dir.resolve()
    module = harness.load_module(gen_dir)
    applied = harness.apply_overrides(module, m["overrides"])
    result = {"mode": a.mode, "n": m["n"], "take": m["take"], "overrides": applied, "seeds": {}}
    for s in a.seeds.split(","):
        result["seeds"][s] = digest_take(module, gen_dir, int(s), m["n"], m["take"])
        print(s, result["seeds"][s], flush=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
