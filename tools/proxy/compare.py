"""CPU proxy: how well does a synthetic sample cover the eval pool, feature by feature?

    python compare.py SAMPLE.npz --pool-dir POOL [--pool-dir POOL2 ...] --out REPORT.json [--seed 0]

Synthetic channels are tail-cropped to lengths drawn from the pool's own length
distribution, so length effects cancel. Reports:
  - per-feature quantiles (pool vs synthetic) and the KS statistic;
  - a two-sample classifier AUC (0.5 = indistinguishable, 1.0 = trivially separable);
  - "realness" by pool group: the mean out-of-fold P(real) of pool series per
    domain / freq / dgp_class. High values mark parts of the pool the corpus does
    not cover.
This is a screening signal only; GPU duels decide.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURE_NAMES, MIN_LENGTH, series_features  # noqa: E402

QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
GROUP_FIELDS = ("domain", "freq", "dgp_class")
CV_FOLDS = 5


# ── pool ───────────────────────────────────────────────────────────────────

def load_pool_meta(pool_dir: Path) -> dict:
    return json.loads((pool_dir / "metadata.json").read_text())


def pool_channels(arr: np.ndarray) -> list[np.ndarray]:
    return list(np.atleast_2d(arr).astype(np.float64))


def load_pool(pool_dirs: list[Path]):
    feats, groups, lengths = [], [], []
    for pool_dir in pool_dirs:
        meta = load_pool_meta(pool_dir)
        for path in sorted(pool_dir.glob("*.npy")):
            info = meta.get(path.stem, {})
            for ch in pool_channels(np.load(path)):
                f = series_features(ch)
                if f is None:
                    continue
                feats.append(f)
                groups.append({k: str(info.get(k)) for k in GROUP_FIELDS})
                lengths.append(int(np.isfinite(ch).sum()))
    return np.asarray(feats), groups, np.asarray(lengths)


# ── synthetic ──────────────────────────────────────────────────────────────

def load_sample(path: Path):
    doc = np.load(path)
    return doc["channels"], json.loads(str(doc["meta"]))


def crop_tail(ch: np.ndarray, length: int) -> np.ndarray:
    return ch[-max(int(length), MIN_LENGTH):]


def synthetic_features(channels: np.ndarray, pool_lengths: np.ndarray, rng) -> np.ndarray:
    lengths = rng.choice(pool_lengths, size=channels.shape[0])
    rows = (series_features(crop_tail(ch, n)) for ch, n in zip(channels, lengths))
    return np.asarray([f for f in rows if f is not None])


# ── pad stripping (eval pads short histories too; compare content, not pads) ──

def strip_leading_pad(ch: np.ndarray) -> np.ndarray:
    differs = np.flatnonzero(ch != ch[0])
    return ch[max(int(differs[0]) - 1, 0):] if differs.size else ch


def synthetic_features_stripped(channels: np.ndarray, pool_lengths: np.ndarray, rng) -> np.ndarray:
    lengths = rng.choice(pool_lengths, size=channels.shape[0])
    rows = (series_features(crop_tail(strip_leading_pad(ch), n)) for ch, n in zip(channels, lengths))
    return np.asarray([f for f in rows if f is not None])


# ── statistics ─────────────────────────────────────────────────────────────

def ks_statistic(a: np.ndarray, b: np.ndarray) -> float:
    grid = np.sort(np.concatenate([a, b]))
    ca = np.searchsorted(np.sort(a), grid, side="right") / a.size
    cb = np.searchsorted(np.sort(b), grid, side="right") / b.size
    return float(np.abs(ca - cb).max())


def feature_table(pool: np.ndarray, syn: np.ndarray) -> dict:
    out = {}
    for j, name in enumerate(FEATURE_NAMES):
        out[name] = {"ks": round(ks_statistic(pool[:, j], syn[:, j]), 4),
                     "pool_q": np.round(np.quantile(pool[:, j], QUANTILES), 3).tolist(),
                     "syn_q": np.round(np.quantile(syn[:, j], QUANTILES), 3).tolist()}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["ks"]))


def balanced_indices(n_pool: int, n_syn: int, rng):
    n = min(n_pool, n_syn)
    return rng.choice(n_pool, n, replace=False), rng.choice(n_syn, n, replace=False)


def out_of_fold_proba(x: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=seed)
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=seed)
    return cross_val_predict(clf, x, y, cv=cv, method="predict_proba")[:, 1]


def auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p))


def realness_by_group(p_real: np.ndarray, groups: list[dict], field: str) -> dict:
    sums: dict[str, list] = {}
    for p, g in zip(p_real, groups):
        sums.setdefault(g[field], []).append(float(p))
    rows = {k: {"n": len(v), "p_real": round(float(np.mean(v)), 3)} for k, v in sums.items()}
    return dict(sorted(rows.items(), key=lambda kv: -kv[1]["p_real"]))


def classifier_report(pool: np.ndarray, groups: list[dict], syn: np.ndarray, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    ip, isyn = balanced_indices(len(pool), len(syn), rng)
    x = np.concatenate([pool[ip], syn[isyn]])
    y = np.concatenate([np.ones(len(ip)), np.zeros(len(isyn))])
    p = out_of_fold_proba(x, y, seed)
    pool_groups = [groups[i] for i in ip]
    p_pool = p[:len(ip)]
    return {"auc": round(auc(y, p), 4), "n_per_class": int(len(ip)),
            "realness": {f: realness_by_group(p_pool, pool_groups, f) for f in GROUP_FIELDS}}


# ── cli ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample", type=Path)
    ap.add_argument("--pool-dir", type=Path, action="append", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--keep-pad", action="store_true",
                    help="Keep the leading constant pad of synthetic channels (default: strip it).")
    args = ap.parse_args()

    pool, groups, lengths = load_pool(args.pool_dir)
    channels, meta = load_sample(args.sample)
    featurize = synthetic_features if args.keep_pad else synthetic_features_stripped
    syn = featurize(channels, lengths, np.random.default_rng(args.seed))
    meta = {**meta, "keep_pad": bool(args.keep_pad)}
    report = {"sample": meta, "pool_dirs": [str(p) for p in args.pool_dir],
              "n_pool": int(len(pool)), "n_syn": int(len(syn)),
              "classifier": classifier_report(pool, groups, syn, args.seed),
              "features": feature_table(pool, syn)}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"auc": report["classifier"]["auc"], "n_pool": report["n_pool"],
                      "n_syn": report["n_syn"],
                      "top_ks": {k: v["ks"] for k, v in list(report["features"].items())[:6]}}, indent=2))


if __name__ == "__main__":
    main()
