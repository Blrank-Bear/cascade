"""Transfer proxy: does a corpus teach a small forecaster to forecast the real pool?

    python transfer.py SAMPLE.npz [SAMPLE2.npz ...] --chain-toml CFG --pool-dir POOL [...]
                       [--steps 3000] [--seeds 0,1] [--out REPORT.json]

For each sample (from sample.py): cut (512 context, 64 horizon) training windows
from its channels, train a small quantile MLP on CPU, then score it on the v2
verdict-ladder h=64 windows of each pool (history last 512, first-value left pad
as at eval). Reports sqrt(geomean WQL x geomean MASE) per sample, the same form as
the chain score; lower is better. Only rank differences larger than the seed spread
mean anything. GPU duels decide.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CTX = 512
HORIZON = 64
QUANTILES = np.asarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
WINDOWS_PER_CHANNEL = 8
BATCH = 256
EPS = 1e-8

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "duel"))


# ── windows ────────────────────────────────────────────────────────────────

def left_pad(x: np.ndarray, n: int) -> np.ndarray:
    x = x[-n:]
    return np.concatenate([np.full(n - x.size, x[0]), x]) if x.size < n else x


def train_windows(channels: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    L = channels.shape[1]
    ends = rng.integers(CTX // 4, L - HORIZON + 1, size=(channels.shape[0], WINDOWS_PER_CHANNEL))
    xs, ys = [], []
    for ch, row in zip(channels.astype(np.float64), ends):
        for e in row:
            xs.append(left_pad(ch[:e], CTX))
            ys.append(ch[e:e + HORIZON])
    return np.asarray(xs), np.asarray(ys)


def pool_train_channels(pool_dir: Path) -> list[np.ndarray]:
    out = []
    for path in sorted(pool_dir.glob("*.npy")):
        for ch in np.atleast_2d(np.load(path)).astype(np.float64):
            ch = ch[np.isfinite(ch)]
            if ch.size >= CTX // 4 + HORIZON:
                out.append(ch)
    return out


def train_windows_ragged(channels: list[np.ndarray], rng) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for ch in channels:
        for e in rng.integers(CTX // 4, ch.size - HORIZON + 1, size=WINDOWS_PER_CHANNEL):
            xs.append(left_pad(ch[:e], CTX))
            ys.append(ch[e:e + HORIZON])
    return np.asarray(xs), np.asarray(ys)


def pool_windows(cfg, pool_dir: Path, round_seed: str):
    import duel
    ws = duel.verdict_windows_local(cfg, pool_dir, round_seed=round_seed, n_windows=4000)
    xs, ys = [], []
    for w in ws:
        if duel.window_horizon(w) != HORIZON:
            continue
        hist = np.atleast_2d(np.asarray(w.history, dtype=np.float64))
        tgt = np.atleast_2d(np.asarray(w.target, dtype=np.float64))
        for h, t in zip(hist, tgt):
            if np.all(np.isfinite(h)) and np.all(np.isfinite(t)):
                xs.append(left_pad(h, CTX))
                ys.append(t)
    return np.asarray(xs), np.asarray(ys)


class ChainEval:
    """h=64 eval windows with what the chain metric needs: full history and seasonal period."""

    def __init__(self, xs, ys, hists, periods):
        self.x, self.y, self.hists, self.periods = xs, ys, hists, periods


def pool_windows_chain(cfg, pool_dir: Path, round_seed: str) -> ChainEval:
    import duel
    from cascade.eval.scoring import _resolve_seasonal_period
    ws = duel.verdict_windows_local(cfg, pool_dir, round_seed=round_seed, n_windows=4000)
    xs, ys, hists, periods = [], [], [], []
    for w in ws:
        if duel.window_horizon(w) != HORIZON:
            continue
        period = _resolve_seasonal_period(w.metadata)
        hist = np.atleast_2d(np.asarray(w.history, dtype=np.float64))
        tgt = np.atleast_2d(np.asarray(w.target, dtype=np.float64))
        for h, t in zip(hist, tgt):
            if np.all(np.isfinite(h)) and np.all(np.isfinite(t)):
                xs.append(left_pad(h, CTX))
                ys.append(t)
                hists.append(h)
                periods.append(period)
    return ChainEval(np.asarray(xs), np.asarray(ys), hists, periods)


def chain_wql(q: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-window WQL; all-zero targets are NaN (masked), as in cascade.eval.crps."""
    err = y[..., None] - q
    loss = np.maximum(QUANTILES * err, (QUANTILES - 1.0) * err).mean(axis=-1).sum(axis=-1)
    denom = np.abs(y).sum(axis=-1)
    return np.where(denom > 0, 2.0 * loss / np.where(denom > 0, denom, 1.0), np.nan)


def chain_mase(q: np.ndarray, ev: ChainEval) -> np.ndarray:
    from cascade.eval.mase import mase
    median = q[..., QUANTILES.size // 2]
    return np.asarray([mase(m, t, h, p) for m, t, h, p in zip(median, ev.y, ev.hists, ev.periods)])


def chain_score(q: np.ndarray, ev: ChainEval) -> dict:
    """sqrt(geomean WQL x geomean MASE) with the chain's floors (1e-12 WQL, 1e-9 MASE)."""
    wql = chain_wql(q, ev.y)
    wql_g = float(np.exp(np.log(np.maximum(wql[np.isfinite(wql)], 1e-12)).mean()))
    mase_g = float(np.exp(np.log(np.maximum(chain_mase(q, ev), 1e-9)).mean()))
    return {"wql": round(wql_g, 5), "mase": round(mase_g, 5),
            "score": round(float(np.sqrt(max(wql_g, 1e-12) * max(mase_g, 1e-12))), 5)}


def hold_mask(ev: ChainEval) -> np.ndarray:
    return np.asarray([np.all(t == x[-1]) for t, x in zip(ev.y, ev.x)])


def geomean_mase_split(q: np.ndarray, ev: ChainEval) -> dict:
    """Geomean MASE on exact-hold windows vs. the rest: where a corpus wins or loses."""
    logm = np.log(np.maximum(chain_mase(q, ev), 1e-9))
    hold = hold_mask(ev)
    return {"hold": round(float(np.exp(logm[hold].mean())), 8) if hold.any() else None,
            "other": round(float(np.exp(logm[~hold].mean())), 5)}


def exact_hold_fraction(ev: ChainEval) -> float:
    return float(np.mean([np.all(t == x[-1]) for t, x in zip(ev.y, ev.x)]))


# ── normalisation (per window, from the context only) ──────────────────────

def norm_stats(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Last value and mean |step|: a zero model output is the naive forecast."""
    loc = x[:, -1:]
    step = np.abs(np.diff(x, axis=1)).mean(axis=1, keepdims=True)
    scale = np.maximum(step, np.maximum(np.abs(loc), 1.0) * 1e-6)
    return loc, scale


def normalise(x: np.ndarray, y: np.ndarray):
    loc, scale = norm_stats(x)
    return (x - loc) / scale, (y - loc) / scale, loc, scale


INPUT_ASINH = False


def model_input(xn: np.ndarray) -> np.ndarray:
    return np.arcsinh(xn) if INPUT_ASINH else np.clip(xn, -50, 50)


# ── model ──────────────────────────────────────────────────────────────────

def build_model(torch):
    """Zero-initialised head: the untrained model is exactly the naive forecast."""
    nn = torch.nn
    head = nn.Linear(512, HORIZON * QUANTILES.size)
    nn.init.zeros_(head.weight)
    nn.init.zeros_(head.bias)
    return nn.Sequential(nn.Linear(CTX, 512), nn.GELU(), nn.Linear(512, 512), nn.GELU(), head)


def pinball(torch, pred, y):
    q = torch.as_tensor(QUANTILES, dtype=pred.dtype)
    err = y[..., None] - pred.view(pred.shape[0], HORIZON, QUANTILES.size)
    return torch.maximum(q * err, (q - 1.0) * err).mean()


def train_model(x: np.ndarray, y: np.ndarray, steps: int, seed: int):
    import torch
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    xn, yn, _, _ = normalise(x, y)
    xt = torch.as_tensor(model_input(xn), dtype=torch.float32)
    yt = torch.as_tensor(np.arcsinh(yn), dtype=torch.float32)  # asinh-space quantiles (monotone)
    model = build_model(torch)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    gen = torch.Generator().manual_seed(seed)
    for _ in range(steps):
        idx = torch.randint(0, xt.shape[0], (BATCH,), generator=gen)
        loss = pinball(torch, model(xt[idx]), yt[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
    return model


def predict(model, x: np.ndarray) -> np.ndarray:
    import torch
    xn, _, loc, scale = normalise(x, np.zeros((x.shape[0], HORIZON)))
    with torch.no_grad():
        out = model(torch.as_tensor(model_input(xn), dtype=torch.float32)).numpy()
    q = np.sinh(np.sort(out.reshape(-1, HORIZON, QUANTILES.size), axis=-1))
    return q * scale[..., None] + loc[..., None]


# ── scoring ────────────────────────────────────────────────────────────────

def window_wql(q: np.ndarray, y: np.ndarray) -> np.ndarray:
    err = y[..., None] - q
    loss = np.maximum(QUANTILES * err, (QUANTILES - 1.0) * err).mean(axis=-1).sum(axis=-1)
    return 2.0 * loss / np.maximum(np.abs(y).sum(axis=-1), EPS)


def window_mase(q: np.ndarray, y: np.ndarray, x: np.ndarray) -> np.ndarray:
    median = q[..., QUANTILES.size // 2]
    naive = np.maximum(np.abs(np.diff(x, axis=1)).mean(axis=1), EPS)
    return np.abs(y - median).mean(axis=1) / naive


def naive_quantiles(x: np.ndarray) -> np.ndarray:
    return np.repeat(x[:, -1:, None], HORIZON, axis=1).repeat(QUANTILES.size, axis=2)


def geomean(v: np.ndarray) -> float:
    return float(np.exp(np.mean(np.log(np.maximum(v, 1e-6)))))


def score(q: np.ndarray, y: np.ndarray, x: np.ndarray) -> dict:
    wql, mase = geomean(window_wql(q, y)), geomean(window_mase(q, y, x))
    return {"wql": round(wql, 5), "mase": round(mase, 5), "score": round(float(np.sqrt(wql * mase)), 5)}


def load_eval(cfg, pool_dir: Path, round_seed: str, simple: bool) -> ChainEval:
    if simple:
        x, y = pool_windows(cfg, pool_dir, round_seed)
        return ChainEval(x, y, None, None)
    return pool_windows_chain(cfg, pool_dir, round_seed)


def eval_score(q: np.ndarray, ev: ChainEval, simple: bool) -> dict:
    if simple:
        return score(q, ev.y, ev.x)
    return {**chain_score(q, ev), "mase_split": geomean_mase_split(q, ev)}


# ── cli ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", type=Path, nargs="+")
    ap.add_argument("--chain-toml", type=Path, required=True)
    ap.add_argument("--pool-dir", type=Path, action="append", required=True)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--round-seed", default="transfer-0")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--asinh", action="store_true", help="arcsinh model inputs instead of clipping.")
    ap.add_argument("--simple-metric", action="store_true",
                    help="Context-step MASE, 1e-6 floors (default: the chain's metric and floors).")
    ap.add_argument("--train-pool", type=Path, action="append", default=[],
                    help="Also train a reference arm on real pool series (use an older snapshot).")
    args = ap.parse_args()
    global INPUT_ASINH
    INPUT_ASINH = bool(args.asinh)

    import duel
    cfg = duel.load_cfg(args.chain_toml)
    evals = {p.name: load_eval(cfg, p, args.round_seed, args.simple_metric) for p in args.pool_dir}
    report = {"steps": args.steps, "metric": "simple" if args.simple_metric else "chain",
              "n_eval": {k: int(v.x.shape[0]) for k, v in evals.items()},
              "exact_hold_fraction": {k: round(exact_hold_fraction(v), 4) for k, v in evals.items()},
              "naive_last": {k: eval_score(naive_quantiles(v.x), v, args.simple_metric) for k, v in evals.items()},
              "samples": {}}
    print("naive_last", json.dumps(report["naive_last"]), flush=True)
    arms = [(s.stem, np.load(s)["channels"], train_windows) for s in args.samples]
    arms += [(f"realpool_{p.name}", pool_train_channels(p), train_windows_ragged) for p in args.train_pool]
    for stem, channels, cutter in arms:
        rows = {}
        for seed in (int(s) for s in args.seeds.split(",")):
            x, y = cutter(channels, np.random.default_rng(seed))
            model = train_model(x, y, args.steps, seed)
            rows[str(seed)] = {k: eval_score(predict(model, v.x), v, args.simple_metric) for k, v in evals.items()}
        mean = float(np.mean([s["score"] for r in rows.values() for s in r.values()]))
        report["samples"][stem] = {"mean_score": round(mean, 5), "by_seed": rows}
        print(stem, round(mean, 5), json.dumps(rows), flush=True)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
