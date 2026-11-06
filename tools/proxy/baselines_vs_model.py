"""Where does our trained model lose to trivial forecasters? (finds the generator-fixable error)

    python -I baselines_vs_model.py --chain-toml CFG --pool-dir POOL --round-seed g-0 --n-windows 2000 \
        --model-scores SCORES.json [--out R.json]

Rebuilds exactly the verdict windows the model was scored on (tools/duel/duel.py verdict_windows_local),
scores three trivial sample forecasters with the chain's own scorer, pairs rows with the model's score file,
and reports per horizon x domain: geomean ratio baseline/model (< 1 = baseline better) and the share of
windows where the best baseline beats the model. Wherever a trivial forecast beats the trained model, the
generator taught the wrong behaviour for that kind of series -> fixable by changing the training data.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "duel"))
import duel  # noqa: E402

FLOOR_M, FLOOR_W = 1e-9, 1e-12
TAIL = 512


def ffill(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64).copy()
    ok = np.isfinite(x)
    if not ok.any():
        return np.zeros_like(x)
    idx = np.where(ok, np.arange(len(x)), 0)
    np.maximum.accumulate(idx, out=idx)
    out = x[idx]
    out[: np.argmax(ok)] = x[np.argmax(ok)]
    return out


def naive_rw(h: np.ndarray, horizon: int, ns: int, rng) -> np.ndarray:
    """Last value + bootstrapped random-walk increments: flat median, sqrt(h) widening."""
    d = np.diff(h[-TAIL:]) if len(h) > 2 else np.zeros(1)
    steps = rng.choice(d, size=(ns, horizon)) if d.size else np.zeros((ns, horizon))
    return h[-1] + np.cumsum(steps, axis=1)


def seasonal_naive(h: np.ndarray, horizon: int, ns: int, rng, period: int) -> np.ndarray:
    """Repeat the last season; noise from bootstrapped seasonal differences (no widening)."""
    p = period if 1 < period < len(h) // 2 else 1
    base = np.resize(h[-p:], horizon) if p > 1 else np.full(horizon, h[-1])
    r = (h[p:] - h[:-p])[-TAIL:] if len(h) > p else np.zeros(1)
    return base + rng.choice(r, size=(ns, horizon))


def climatology(h: np.ndarray, horizon: int, ns: int, rng) -> np.ndarray:
    """iid resample of the recent history: flat median, constant spread."""
    tail = h[-min(len(h), max(4 * horizon, 64)):]
    return rng.choice(tail, size=(ns, horizon))


def make_forecaster(kind: str, period_of, seed: int):
    rng = np.random.default_rng(seed)

    def fn(history: np.ndarray, horizon: int, ns: int) -> np.ndarray:
        hist = np.atleast_2d(history)
        out = []
        for c in range(hist.shape[0]):
            h = ffill(hist[c])
            if kind == "naive_rw":
                s = naive_rw(h, horizon, ns, rng)
            elif kind == "seasonal_naive":
                s = seasonal_naive(h, horizon, ns, rng, period_of())
            else:
                s = climatology(h, horizon, ns, rng)
            out.append(np.nan_to_num(s))
        return np.stack(out)
    return fn


def half_log_err(row) -> float | None:
    m = row["mase"]
    q, a = row["qloss_per_q"], row["abs_target"]
    if m is None or not q or not a or a <= 0:
        return None
    w = 2.0 * float(np.sum(q)) / (len(q) * a)
    return 0.5 * (math.log(max(m, FLOOR_M)) + math.log(max(w, FLOOR_W)))


def score_baseline(kind: str, windows, cfg) -> list[dict]:
    from cascade.eval.scoring import _resolve_seasonal_period, score_joint_forecaster_on_windows
    rows = []
    for w in windows:  # one window at a time so the seasonal period is the window's own
        fn = make_forecaster(kind, lambda: _resolve_seasonal_period(w.metadata), seed=hash(w.series_id) & 0xFFFF)
        for s in score_joint_forecaster_on_windows(fn, [w], cfg.eval.num_samples):
            d = duel.score_to_dict(s)
            d["horizon"] = duel.window_horizon(w)
            rows.append(d)
    return rows


def paired(model_rows: list[dict], base_rows: list[dict]) -> None:
    if len(model_rows) != len(base_rows):
        raise SystemExit(f"row count mismatch: model {len(model_rows)} vs baseline {len(base_rows)}")
    for a, b in zip(model_rows, base_rows):
        if (a["series_id"], a.get("channel")) != (b["series_id"], b.get("channel")):
            raise SystemExit(f"window order mismatch at {a['series_id']} vs {b['series_id']}")


def report(model_rows, baselines: dict) -> dict:
    cells = defaultdict(lambda: defaultdict(list))
    for i, mr in enumerate(model_rows):
        em = half_log_err(mr)
        if em is None:
            continue
        key = (str(mr["horizon"]), mr.get("domain") or "?")
        errs = {k: half_log_err(rows[i]) for k, rows in baselines.items()}
        errs = {k: v for k, v in errs.items() if v is not None}
        for k, v in errs.items():
            cells[key][k].append(v - em)
        if errs:
            cells[key]["best_of"].append(min(errs.values()) - em)
    out = {}
    names = list(baselines) + ["best_of"]
    print(f"{'h':>4s} {'domain':12s} {'n':>5s} " + " ".join(f"{k[:14]:>14s}" for k in names) + "  win%best  fixable")
    total_fix = 0.0
    for key in sorted(cells, key=lambda k: (int(k[0]), k[1])):
        c = cells[key]
        n = len(c["best_of"])
        means = {k: float(np.mean(c[k])) for k in names if c[k]}
        wins = float(np.mean([d < 0 for d in c["best_of"]]))
        fix = float(-np.sum([min(0.0, d) for d in c["best_of"]]))  # error the model could shed by matching the best trivial forecast
        total_fix += fix
        out["|".join(key)] = {"n": n, "mean_delta": means, "best_win_share": wins, "fixable_units": fix}
        print(f"{key[0]:>4s} {key[1][:12]:12s} {n:5d} " + " ".join(f"{means.get(k, float('nan')):14.3f}" for k in names)
              + f"  {wins * 100:7.1f}% {fix:8.0f}")
    n_all = sum(v["n"] for v in out.values())
    print(f"\nmean delta = baseline half-log-error minus model's (negative = baseline better).")
    print(f"fixable units (best trivial forecast per window, where it beats the model): {total_fix:.0f}; "
          f"a 1% metric gain needs {0.01 * n_all:.0f}")
    return {"cells": out, "fixable_total": total_fix, "one_pct_units": 0.01 * n_all}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain-toml", type=Path, required=True)
    ap.add_argument("--pool-dir", type=Path, required=True)
    ap.add_argument("--round-seed", default="g-0")
    ap.add_argument("--n-windows", type=int, default=2000)
    ap.add_argument("--model-scores", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    cfg = duel.load_cfg(a.chain_toml)
    windows = duel.verdict_windows_local(cfg, a.pool_dir.resolve(), round_seed=a.round_seed, n_windows=a.n_windows)
    model_rows = json.loads(a.model_scores.read_text())["scores"]
    baselines = {}
    for kind in ("naive_rw", "seasonal_naive", "climatology"):
        baselines[kind] = score_baseline(kind, windows, cfg)
        paired(model_rows, baselines[kind])
    res = report(model_rows, baselines)
    if a.out:
        a.out.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
