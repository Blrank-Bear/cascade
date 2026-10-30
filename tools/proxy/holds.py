"""Hold conditional: P(target is an exact hold | trailing constant run of the context).

Exact-hold windows dominate the log-geomean round metric (see notes/V2_EVAL_FACTS.md),
so what a corpus teaches about *when* the future holds exactly matters. This compares
that conditional on eval windows (v2 ladder) and on corpus channels (random cuts).

    python holds.py --chain-toml CFG --pool-dir POOL [...] [--sample SAMPLE.npz ...]
                    [--horizon 64] [--out REPORT.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

RUN_EDGES = (0, 1, 4, 16, 64, 256, 1024, 4096)
CUTS_PER_CHANNEL = 8

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "duel"))


def trailing_run(x: np.ndarray) -> int:
    """Number of trailing steps equal to the last value (0 = the last step changed)."""
    differs = np.flatnonzero(x[::-1] != x[-1])
    return int(differs[0]) - 1 if differs.size else int(x.size) - 1


def is_hold(x: np.ndarray, y: np.ndarray) -> bool:
    return bool(np.all(y == x[-1]))


def bucket_of(run: int) -> str:
    for lo, hi in zip(RUN_EDGES[:-1], RUN_EDGES[1:]):
        if lo <= run < hi:
            return f"[{lo},{hi})"
    return f"[{RUN_EDGES[-1]},inf)"


def conditional(pairs) -> dict:
    stats: dict[str, list] = {}
    for x, y in pairs:
        stats.setdefault(bucket_of(trailing_run(x)), []).append(is_hold(x, y))
    total = sum(len(v) for v in stats.values())
    order = [bucket_of(lo) for lo in RUN_EDGES[:-1]]
    return {b: {"share": round(len(stats[b]) / total, 4), "p_hold": round(float(np.mean(stats[b])), 4)}
            for b in order if b in stats} | {"overall_p_hold": round(float(np.mean(
                [h for v in stats.values() for h in v])), 4)}


def eval_pairs(cfg, pool_dir: Path, horizon: int):
    import duel
    for w in duel.verdict_windows_local(cfg, pool_dir, round_seed="holds-0", n_windows=4000):
        if duel.window_horizon(w) != horizon:
            continue
        for h, t in zip(np.atleast_2d(np.asarray(w.history, float)), np.atleast_2d(np.asarray(w.target, float))):
            h = h[np.isfinite(h)]
            if h.size and np.all(np.isfinite(t)):
                yield h, t


def corpus_pairs(channels: np.ndarray, horizon: int, rng):
    L = channels.shape[1]
    for ch in channels.astype(np.float64):
        for e in rng.integers(256, L - horizon + 1, CUTS_PER_CHANNEL):
            yield ch[:e], ch[e:e + horizon]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain-toml", type=Path, required=True)
    ap.add_argument("--pool-dir", type=Path, action="append", required=True)
    ap.add_argument("--sample", type=Path, action="append", default=[])
    ap.add_argument("--horizon", type=int, default=64)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    import duel
    cfg = duel.load_cfg(args.chain_toml)
    report = {"horizon": args.horizon,
              "eval": {p.name: conditional(eval_pairs(cfg, p, args.horizon)) for p in args.pool_dir},
              "corpus": {s.stem: conditional(corpus_pairs(np.load(s)["channels"], args.horizon,
                                                          np.random.default_rng(0))) for s in args.sample}}
    text = json.dumps(report, indent=1)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
