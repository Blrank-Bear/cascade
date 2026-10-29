"""Measure a generator under v2 CPU-child limits: 1 core, RLIMIT_AS, BLAS threads = 1.

    python measure.py GEN_DIR [--seconds 120] [--as-mb 2048] [--seed 2**62+5]

Prints JSON: values/s, series/s, shape mix, time to first yield, peak memory.
v2 needs ~1.5625e9 values per child in 5400 s => >= 289,352 values/s.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

V2_TARGET_VALUES_PER_S = 1.5625e9 / 5400


def limit_address_space(mb: int) -> None:
    limit = mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def load_generator_module(gen_dir: Path):
    sys.path.insert(0, str(gen_dir))
    spec = importlib.util.spec_from_file_location("generator", gen_dir / "generator.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generator"] = module
    spec.loader.exec_module(module)
    return module


def proc_status_kb(key: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1])
    return -1


def record_values(item) -> np.ndarray:
    return np.asarray(item["values"] if isinstance(item, dict) else item)


def run(gen_dir: Path, seconds: float, seed: int) -> dict:
    t_import = time.perf_counter()
    module = load_generator_module(gen_dir)
    gen = module.Generator(str(gen_dir), seed=seed)
    t_start = time.perf_counter()
    values = 0
    series = 0
    first = None
    shapes: dict[str, int] = {}
    dtypes: dict[str, int] = {}
    for item in gen.generate(50_000_000):
        arr = record_values(item)
        if first is None:
            first = time.perf_counter() - t_start
        values += arr.size
        series += 1
        key = "x".join(map(str, arr.shape))
        shapes[key] = shapes.get(key, 0) + 1
        dtypes[arr.dtype.str] = dtypes.get(arr.dtype.str, 0) + 1
        if time.perf_counter() - t_start >= seconds:
            break
    elapsed = time.perf_counter() - t_start
    steady = elapsed - (first or 0.0)
    return {
        "import_s": round(t_start - t_import, 2),
        "first_yield_s": round(first or -1, 2),
        "elapsed_s": round(elapsed, 2),
        "series": series,
        "values": values,
        "values_per_s": round(values / elapsed),
        "values_per_s_after_first": round((values / steady) if steady > 0 else 0),
        "v2_ratio": round(values / elapsed / V2_TARGET_VALUES_PER_S, 3),
        "shapes": dict(sorted(shapes.items(), key=lambda kv: -kv[1])),
        "dtypes": dtypes,
        "vm_peak_mb": round(proc_status_kb("VmPeak") / 1024),
        "rss_peak_mb": round(proc_status_kb("VmHWM") / 1024),
        "threads": int(proc_status_kb("Threads")),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gen_dir", type=Path)
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--as-mb", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=2**62 + 5)
    args = ap.parse_args()
    if args.as_mb > 0:
        limit_address_space(args.as_mb)
    try:
        result = run(args.gen_dir.resolve(), args.seconds, args.seed)
        result["ok"] = True
    except BaseException as exc:  # report MemoryError etc. as data
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500],
                  "vm_peak_mb": round(proc_status_kb("VmPeak") / 1024)}
    result["as_mb"] = args.as_mb
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
