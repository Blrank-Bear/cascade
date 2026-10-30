"""Numerics scan: how close does a corpus get to the v2 joint-loss overflow?

The v2 pyramid trainer standardises each channel causally (expanding mean/std from the
series start, std floored at 1e-5; upstream cascade/trainer/pyramid_model.py
causal_standardize) and feeds truth = (next patch - loc) / scale to the energy-score
loss without clamping. A float32 norm over a 32-point patch overflows once |truth|
exceeds about 3e18, which kills training as "non-finite loss" (a burned submission).

For each channel this computes, with upstream's own causal_standardize, the max |truth|
over all patch boundaries, and reports the distribution plus the worst channels.

    python numerics.py SAMPLE.npz [...] [--top 10]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

PATCH = 32
OVERFLOW = 3.0e18
LEVELS = (1e6, 1e9, 1e12, 1e15, OVERFLOW)


def max_truth(channels: np.ndarray) -> np.ndarray:
    """Max |(next patch - loc_t) / scale_t| per channel, exactly as the trainer forms it."""
    from cascade.trainer.pyramid_model import causal_standardize
    x = torch.as_tensor(np.nan_to_num(channels.astype(np.float32)), dtype=torch.float32)
    n, L = x.shape
    p = L // PATCH
    x = x[:, :p * PATCH]
    _, loc, scale = causal_standardize(x.double())
    loc = loc.reshape(n, p, PATCH)[:, :-1, -1, None].float()
    scale = scale.reshape(n, p, PATCH)[:, :-1, -1, None].float()
    truth = (x.reshape(n, p, PATCH)[:, 1:] - loc) / scale
    return truth.abs().amax(dim=(1, 2)).double().numpy()


def describe(values: np.ndarray, channels: np.ndarray, top: int) -> dict:
    order = np.argsort(-values)[:top]
    return {"n": int(values.size),
            "frac_over": {f"{lv:.0e}": float((values > lv).mean()) for lv in LEVELS},
            "max": float(values.max()),
            "worst": [{"i": int(i), "max_truth": float(values[i]),
                       "max_abs": float(np.abs(channels[i]).max()),
                       "first_change": int(np.argmax(channels[i] != channels[i][0])),
                       "start_value": float(channels[i][0])} for i in order]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", type=Path, nargs="+")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()
    for s in args.samples:
        ch = np.load(s)["channels"]
        v = np.concatenate([max_truth(ch[i:i + 4096]) for i in range(0, len(ch), 4096)])
        print(s.stem, json.dumps(describe(v, ch, args.top)), flush=True)


if __name__ == "__main__":
    main()
