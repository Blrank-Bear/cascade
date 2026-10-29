"""Local king-vs-challenger duel with the validator's own scoring and judging code.

Three steps, each cached on disk so GPU time is spent once per generator:

    duel.py train GEN_DIR  --chain-toml CFG --out CKPT_DIR [--hours H] [--seed S] [--device cuda]
    duel.py score CKPT_DIR --chain-toml CFG --pool-dir POOL --out SCORES.json [--round-seed R] [--n-windows 4000]
    duel.py judge KING.json CHAL.json --chain-toml CFG [--baseline INIT.json] [--margin M] [--round-seed R]

`score` draws the v2 verdict ladder (horizons 64/256/720, domain-balanced, seeded
like a settlement) with `ladder_windows_for_round`, and scores with
`evaluate_checkpoint`. `judge` runs `cascade.eval.koth.evaluate_round`: the
source-family cluster bootstrap, LCB and margin. Same seeds, same model and same
budget on both sides, or the comparison means nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

V2_HORIZONS = (64, 256, 720)
V2_N_WINDOWS = 4000
RANDOM_INIT_LEVEL_MARGIN = 0.01


# ── config / contract ──────────────────────────────────────────────────────

def load_cfg(chain_toml: Path):
    from cascade.shared.config import load_chain_config
    return load_chain_config(chain_toml)


def training_contract(cfg, hours: float | None):
    contract = cfg.screen_contract()
    if hours is None:
        return contract
    return contract.for_hours(hours, guard_factor=cfg.round.heat_guard_factor,
                              guard_floor_seconds=cfg.round.heat_guard_floor_seconds)


# ── train ──────────────────────────────────────────────────────────────────

def train_checkpoint(gen_dir: Path, cfg, contract, *, seed: int, device: str, out_dir: Path) -> dict:
    from cascade.miner.local_corpus import local_round_stream
    from cascade.trainer.contract import RoundSeeds
    from cascade.trainer.main import _load_trainer

    seeds = RoundSeeds.derive(seed, cfg.training)
    trainer = _load_trainer("cascade.trainer.toto2_trainer:Toto2Trainer")
    if hasattr(trainer, "device"):
        trainer.device = device
    out_dir.mkdir(parents=True, exist_ok=True)
    with local_round_stream(
        contract.corpus_mode, gen_dir, seeds.generation_seed, cfg.generator,
        generation=cfg.generation, token_budget=contract.train_tokens, use_sandbox=False,
        blocked=cfg.static_guard.blocked,
        seed_mix=int(getattr(contract, "gen_seed_mix", 1) or 1),
        budget_denomination=getattr(contract, "budget_denomination", "points"),
        corpus_epochs=int(getattr(contract, "corpus_epochs", 0) or 0),
    ) as rs:
        result = trainer.train(rs.series(), contract, training_seed=seeds.training_seed,
                               token_budget=contract.train_tokens, out_dir=out_dir)
        digest, n_series = rs.digest, rs.n_series
    return {"checkpoint": str(result.local_dir), "corpus_digest": digest, "n_series": n_series,
            "train_seconds": result.train_seconds, "seed": seed, "generator": str(gen_dir)}


# ── score ──────────────────────────────────────────────────────────────────

def verdict_windows_local(cfg, pool_dir: Path, *, round_seed, n_windows: int):
    from cascade.validator.pool import window_source_from_dir
    from cascade.validator.windows import ladder_windows_for_round

    source = window_source_from_dir(pool_dir, cfg, label=f"dir={pool_dir}")
    return ladder_windows_for_round(
        source, horizons=V2_HORIZONS, n_windows=n_windows,
        context_length=cfg.eval.context_length, round_seed=round_seed, block=None,
    )


def score_windows(ckpt: Path, windows, cfg, *, device: str) -> list:
    from cascade.validator.evaluator import evaluate_checkpoint
    return evaluate_checkpoint(ckpt, windows, num_samples=cfg.eval.num_samples, device=device)


def score_to_dict(score) -> dict:
    d = asdict(score)
    d["qloss_per_q"] = np.asarray(score.qloss_per_q, dtype=np.float64).tolist()
    d["quantile_levels"] = list(score.quantile_levels)
    return d


def score_from_dict(d: dict):
    from cascade.eval.scoring import WindowScore
    return WindowScore(**{**d, "qloss_per_q": np.asarray(d["qloss_per_q"], dtype=np.float64),
                          "quantile_levels": tuple(d["quantile_levels"])})


def window_horizon(window) -> int:
    return int(np.asarray(window.target).shape[-1])


def save_scores(path: Path, scores, windows, meta: dict) -> None:
    rows = [dict(score_to_dict(s), horizon=window_horizon(w)) for s, w in zip(scores, windows)]
    path.write_text(json.dumps({"meta": meta, "scores": rows}) + "\n")


def load_scores(path: Path):
    doc = json.loads(path.read_text())
    rows = doc["scores"]
    horizons = [r.pop("horizon", None) for r in rows]
    return [score_from_dict(r) for r in rows], horizons, doc["meta"]


# ── judge ──────────────────────────────────────────────────────────────────

def level_params(cfg, margin: float | None):
    params = cfg.judged_level_params(cfg.koth_params(block=None), None)
    if margin is None:
        return params
    return replace(params, win_margin_start=margin, win_margin_end=margin)


def increment_params(cfg, margin: float | None):
    params = replace(cfg.koth_params(block=None), margin_mode="increment")
    if margin is None:
        return params
    return replace(params, win_margin_start=margin, win_margin_end=margin)


def check_paired(a: dict, b: dict) -> None:
    keys = ("pool_dir", "round_seed", "n_windows")
    if any(a.get(k) != b.get(k) for k in keys):
        raise SystemExit(f"unpaired score files: {[(k, a.get(k), b.get(k)) for k in keys]}")


def judge(cfg, king_path: Path, chal_path: Path, baseline_path: Path | None,
          margin: float | None, round_seed) -> dict:
    from cascade.eval.koth import evaluate_round

    king, horizons, king_meta = load_scores(king_path)
    chal, _, chal_meta = load_scores(chal_path)
    check_paired(king_meta, chal_meta)
    baseline = load_scores(baseline_path)[0] if baseline_path else None
    params = increment_params(cfg, margin) if baseline else level_params(cfg, margin)
    result = evaluate_round(king, chal, params, seed=round_seed, baseline_scores=baseline)
    out = {k: v for k, v in asdict(result).items() if not isinstance(v, np.ndarray)}
    out["per_horizon_local"] = per_horizon_geomeans(king, chal, horizons)
    return out


def per_horizon_geomeans(king, chal, horizons) -> dict:
    from cascade.eval.scoring import global_geomean
    out = {}
    for h in sorted({h for h in horizons if h is not None}):
        idx = [i for i, x in enumerate(horizons) if x == h]
        k = global_geomean([king[i] for i in idx])
        c = global_geomean([chal[i] for i in idx])
        out[str(h)] = {"n": len(idx), "king": k, "chal": c, "rel_improvement": (k - c) / k if k else None}
    return out


# ── cli ────────────────────────────────────────────────────────────────────

def cmd_train(args) -> dict:
    cfg = load_cfg(args.chain_toml)
    contract = training_contract(cfg, args.hours)
    return train_checkpoint(args.gen_dir.resolve(), cfg, contract, seed=args.seed,
                            device=args.device, out_dir=args.out.resolve())


def cmd_score(args) -> dict:
    cfg = load_cfg(args.chain_toml)
    windows = verdict_windows_local(cfg, args.pool_dir.resolve(), round_seed=args.round_seed,
                                    n_windows=args.n_windows)
    scores = score_windows(args.ckpt.resolve(), windows, cfg, device=args.device)
    meta = {"pool_dir": str(args.pool_dir.resolve()), "round_seed": args.round_seed,
            "n_windows": args.n_windows, "ckpt": str(args.ckpt.resolve())}
    save_scores(args.out, scores, windows, meta)
    from cascade.eval.scoring import global_geomean
    return {"windows": len(scores), "geomean": global_geomean(scores), "out": str(args.out)}


def cmd_judge(args) -> dict:
    cfg = load_cfg(args.chain_toml)
    return judge(cfg, args.king, args.chal, args.baseline, args.margin, args.round_seed)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("gen_dir", type=Path)
    t.add_argument("--chain-toml", type=Path, required=True)
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--hours", type=float, default=None, help="Scaled budget; omit for the full contract.")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--device", default="cpu")
    t.set_defaults(func=cmd_train)
    s = sub.add_parser("score")
    s.add_argument("ckpt", type=Path)
    s.add_argument("--chain-toml", type=Path, required=True)
    s.add_argument("--pool-dir", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--round-seed", default="local-duel-0")
    s.add_argument("--n-windows", type=int, default=V2_N_WINDOWS)
    s.add_argument("--device", default="cpu")
    s.set_defaults(func=cmd_score)
    j = sub.add_parser("judge")
    j.add_argument("king", type=Path)
    j.add_argument("chal", type=Path)
    j.add_argument("--chain-toml", type=Path, required=True)
    j.add_argument("--baseline", type=Path, default=None, help="Init scores -> increment units.")
    j.add_argument("--margin", type=float, default=None,
                   help=f"Override the bar (random-init v2 level bar ~{RANDOM_INIT_LEVEL_MARGIN}).")
    j.add_argument("--round-seed", default="local-duel-0")
    j.set_defaults(func=cmd_judge)
    return ap


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(args.func(args), indent=2, default=str))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
