"""Effective-history check: does the corpus train on contexts as short as eval's?

At eval, a history shorter than 4096 is left-padded with its first value
(pyramid_wrapper._prep), and about 90% of verdict-ladder windows are shorter.
A training channel's "effective history" is 4096 minus its leading run of values
equal to its first value: the same shape eval inputs have.

    python history.py SAMPLE.npz [--eval-ctx CTX.npy ...] --out REPORT.json

`--eval-ctx` takes arrays of eval context lengths (from `eval_ctx.py`); without
it only the corpus side is reported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

LENGTH = 4096
EDGES = (128, 256, 512, 1024, 2048, 3072, 4096)


def leading_run(ch: np.ndarray) -> int:
    differs = np.flatnonzero(ch != ch[0])
    return int(differs[0]) if differs.size else int(ch.size)


def effective_history(channels: np.ndarray) -> np.ndarray:
    return np.asarray([ch.size - leading_run(ch) + 1 for ch in channels])


def bucket_fractions(lengths: np.ndarray) -> dict:
    lengths = np.minimum(lengths, LENGTH)
    lo = 0
    out = {}
    for hi in EDGES:
        out[f"({lo},{hi}]"] = round(float(np.mean((lengths > lo) & (lengths <= hi))), 4)
        lo = hi
    return out


def load_eval_ctx(paths: list[Path]) -> np.ndarray | None:
    if not paths:
        return None
    return np.concatenate([np.load(p) for p in paths])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample", type=Path)
    ap.add_argument("--eval-ctx", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    channels = np.load(args.sample)["channels"]
    hist = effective_history(channels)
    report = {"n_channels": int(hist.size), "corpus": bucket_fractions(hist),
              "corpus_median": int(np.median(hist))}
    ctx = load_eval_ctx(args.eval_ctx)
    if ctx is not None:
        report["eval"] = bucket_fractions(ctx)
        report["eval_median"] = int(np.median(ctx))
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
