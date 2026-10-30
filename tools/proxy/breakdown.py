"""Where does a corpus lose? Per-domain / per-frequency chain-metric breakdown on non-hold windows.

Trains the transfer proxy model (tools/proxy/transfer.py) on each sample, then reports,
per group of h=64 eval windows (domain, freq): the geomean MASE and WQL of the model
and their log-ratio to the naive last-value forecast. Hold windows are excluded (their
precision is measured by transfer.py's split); this is about the "other" ~94%.

    python breakdown.py SAMPLE.npz [...] --chain-toml CFG --pool-dir POOL [...] [--seeds 0,1] [--out R.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "duel"))
import transfer as T  # noqa: E402

GROUP_FIELDS = ("domain", "freq")


def windows_with_meta(cfg, pool_dir: Path, round_seed: str):
    """transfer.pool_windows_chain plus each window's group labels."""
    import duel
    from cascade.eval.scoring import _resolve_seasonal_period
    xs, ys, hists, periods, groups = [], [], [], [], []
    for w in duel.verdict_windows_local(cfg, pool_dir, round_seed=round_seed, n_windows=4000):
        if duel.window_horizon(w) != T.HORIZON:
            continue
        meta = w.metadata or {}
        period = _resolve_seasonal_period(meta)
        label = {f: str(meta.get(f, "?")) for f in GROUP_FIELDS}
        for h, t in zip(np.atleast_2d(np.asarray(w.history, float)), np.atleast_2d(np.asarray(w.target, float))):
            if np.all(np.isfinite(h)) and np.all(np.isfinite(t)):
                xs.append(T.left_pad(h, T.CTX)); ys.append(t); hists.append(h); periods.append(period)
                groups.append(label)
    return T.ChainEval(np.asarray(xs), np.asarray(ys), hists, periods), groups


def log_metrics(q: np.ndarray, ev) -> tuple[np.ndarray, np.ndarray]:
    lm = np.log(np.maximum(T.chain_mase(q, ev), 1e-9))
    wql = T.chain_wql(q, ev.y)
    lw = np.where(np.isfinite(wql), np.log(np.maximum(np.nan_to_num(wql, nan=1.0), 1e-12)), np.nan)
    return lm, lw


def group_table(lm, lw, lm0, lw0, groups, keep) -> dict:
    out = {}
    for field in GROUP_FIELDS:
        labels = np.asarray([g[field] for g in groups])
        rows = {}
        for lab in sorted(set(labels[keep])):
            m = keep & (labels == lab)
            w = m & np.isfinite(lw) & np.isfinite(lw0)
            rows[lab] = {"n": int(m.sum()),
                         "mase": round(float(np.exp(lm[m].mean())), 4),
                         "log_mase_vs_naive": round(float((lm[m] - lm0[m]).mean()), 4),
                         "log_wql_vs_naive": round(float((lw[w] - lw0[w]).mean()), 4) if w.any() else None}
        out[field] = rows
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", type=Path, nargs="+")
    ap.add_argument("--chain-toml", type=Path, required=True)
    ap.add_argument("--pool-dir", type=Path, action="append", required=True)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--round-seed", default="transfer-0")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    import duel
    cfg = duel.load_cfg(args.chain_toml)
    loaded = [windows_with_meta(cfg, p, args.round_seed) for p in args.pool_dir]
    ev = T.ChainEval(np.concatenate([e.x for e, _ in loaded]), np.concatenate([e.y for e, _ in loaded]),
                     [h for e, _ in loaded for h in e.hists], [p for e, _ in loaded for p in e.periods])
    groups = [g for _, gs in loaded for g in gs]
    keep = ~T.hold_mask(ev)
    lm0, lw0 = log_metrics(T.naive_quantiles(ev.x), ev)
    report = {"n_windows": int(ev.x.shape[0]), "n_other": int(keep.sum()), "samples": {}}
    for s in args.samples:
        channels = np.load(s)["channels"]
        lms, lws = [], []
        for seed in (int(v) for v in args.seeds.split(",")):
            x, y = T.train_windows(channels, np.random.default_rng(seed))
            lm, lw = log_metrics(T.predict(T.train_model(x, y, args.steps, seed), ev.x), ev)
            lms.append(lm); lws.append(lw)
        lm, lw = np.mean(lms, axis=0), np.nanmean(lws, axis=0)
        report["samples"][s.stem] = group_table(lm, lw, lm0, lw0, groups, keep)
        print(s.stem, json.dumps(report["samples"][s.stem]), flush=True)
    if args.out:
        args.out.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
