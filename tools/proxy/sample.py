"""Sample channels from a generator's v2 records into an .npz for `compare.py`.

    python sample.py GEN_DIR --out SAMPLE.npz [--records 400] [--per-record 8]
                     [--seeds 0,1] [--mode natural|late] [--cls Generator]

Mode "late" reuses the golden harness's stream-budget overrides, so late-stream
layers are represented in a short run.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HARNESS = Path(__file__).resolve().parents[2] / "tests" / "golden" / "harness.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("golden_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record_values(item) -> np.ndarray:
    return np.atleast_2d(np.asarray(item["values"] if isinstance(item, dict) else item))


def pick_channels(values: np.ndarray, k: int, rng) -> np.ndarray:
    idx = rng.choice(values.shape[0], size=min(k, values.shape[0]), replace=False)
    return values[np.sort(idx)]


def sample_seed(module, cls_name: str, gen_dir: Path, seed: int, records: int, per_record: int):
    gen = getattr(module, cls_name)(str(gen_dir), seed=seed)
    rng = np.random.default_rng([seed & ((1 << 64) - 1), 0x5A3B])
    rows = []
    for count, item in enumerate(gen.generate(records), start=1):
        rows.append(pick_channels(record_values(item), per_record, rng).astype(np.float32))
        if count >= records:
            break
    return np.concatenate(rows, axis=0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gen_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--records", type=int, default=400)
    ap.add_argument("--per-record", type=int, default=8)
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--mode", choices=("natural", "late"), default="natural")
    ap.add_argument("--cls", default="Generator")
    args = ap.parse_args()

    harness = load_harness()
    gen_dir = args.gen_dir.resolve()
    module = harness.load_module(gen_dir)
    applied = harness.apply_overrides(module, harness.LATE_OVERRIDES) if args.mode == "late" else {}
    t0 = time.perf_counter()
    parts = [sample_seed(module, args.cls, gen_dir, int(s), args.records, args.per_record)
             for s in args.seeds.split(",")]
    channels = np.concatenate(parts, axis=0)
    meta = {"gen_dir": str(gen_dir), "mode": args.mode, "cls": args.cls, "seeds": args.seeds,
            "records": args.records, "per_record": args.per_record, "overrides": applied,
            "seconds": round(time.perf_counter() - t0, 1)}
    np.savez_compressed(args.out, channels=channels, meta=json.dumps(meta))
    print(json.dumps({**meta, "channels": int(channels.shape[0])}))


if __name__ == "__main__":
    main()
