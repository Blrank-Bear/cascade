"""Stage-B screening grid: one base arm vs. several switch-config arms, same seed and budget.

    python grid.py ARMS.json --chain-toml CFG --work DIR [--hours 0.5] [--seed 0]
                   [--device cuda] [--pools 3] [--round-seeds grid-0,grid-1] [--margin 0.01]

ARMS.json maps an arm name to its switch files, e.g.
    {"base": {}, "hist55": {"v2_history.json": {"rate": 0.55}},
     "pool2": {"v2_pool2.json": {"rate": 0.25}}}
The arm named "base" is the reference. Every step is cached in DIR (a finished
checkpoint or score file is never recomputed), so the grid can be resumed.
DIR/summary.json holds, per arm and per (pool, round seed), the judge verdict vs. base.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DUEL = Path(__file__).resolve().parent / "duel.py"
GEN_FILES = ("generator.py", "config.json", "requirements.txt")
POOLS_DIR = ROOT / ".claude-work" / "data" / "pools"


def newest_pools(k: int) -> list[Path]:
    pools = sorted((p for p in POOLS_DIR.glob("*-block-*") if (p / ".verified").is_file()),
                   key=lambda p: int(p.name.rsplit("-block-", 1)[1]))
    return pools[-k:]


def build_arm_dir(work: Path, name: str, switches: dict) -> Path:
    d = work / "gen" / name
    d.mkdir(parents=True, exist_ok=True)
    for f in GEN_FILES:
        shutil.copyfile(ROOT / "generator" / f, d / f)
    for fname, body in switches.items():
        (d / fname).write_text(json.dumps(body) + "\n")
    return d


def run_duel(*args) -> dict:
    out = subprocess.run([sys.executable, str(DUEL), *map(str, args)], check=True,
                         capture_output=True, text=True).stdout
    start = out.rfind("
{
")
    return json.loads(out[start + 1:] if start >= 0 else out[out.index("{"):])


def train_arm(gen_dir: Path, ckpt: Path, a) -> None:
    if (ckpt / "train.json").is_file():
        return
    res = run_duel("train", gen_dir, "--chain-toml", a.chain_toml, "--out", ckpt, "--seed", a.seed,
                   "--device", a.device, *(["--hours", a.hours] if a.hours is not None else []))
    (ckpt / "train.json").write_text(json.dumps(res, indent=2) + "\n")


def score_path(work: Path, arm: str, pool: Path, rs: str) -> Path:
    return work / "scores" / f"{arm}__{pool.name}__{rs}.json"


def score_arm(work: Path, arm: str, pool: Path, rs: str, a) -> Path:
    out = score_path(work, arm, pool, rs)
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        run_duel("score", work / "ckpt" / arm, "--chain-toml", a.chain_toml, "--pool-dir", pool,
                 "--out", out, "--round-seed", rs, "--device", a.device, "--n-windows", a.n_windows)
    return out


def judge_arm(work: Path, arm: str, pool: Path, rs: str, a) -> dict:
    res = run_duel("judge", score_path(work, "base", pool, rs), score_path(work, arm, pool, rs),
                   "--chain-toml", a.chain_toml, "--round-seed", rs, "--margin", a.margin)
    keep = ("challenger_wins_round", "lcb", "margin", "king_geomean", "chal_geomean", "n_windows")
    return {**{k: res.get(k) for k in keep}, "per_horizon": res.get("per_horizon_local")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arms", type=Path)
    ap.add_argument("--chain-toml", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--hours", type=float, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--pools", type=int, default=3)
    ap.add_argument("--round-seeds", default="grid-0,grid-1")
    ap.add_argument("--margin", type=float, default=0.01)
    ap.add_argument("--n-windows", type=int, default=4000)
    a = ap.parse_args()

    arms = json.loads(a.arms.read_text())
    if "base" not in arms:
        raise SystemExit("ARMS.json needs a 'base' arm")
    work = a.work.resolve()
    pools = newest_pools(a.pools)
    seeds = a.round_seeds.split(",")
    for name, switches in arms.items():
        train_arm(build_arm_dir(work, name, switches), work / "ckpt" / name, a)
        for pool in pools:
            for rs in seeds:
                score_arm(work, name, pool, rs, a)
    summary = {name: {f"{p.name}|{rs}": judge_arm(work, name, p, rs, a) for p in pools for rs in seeds}
               for name in arms if name != "base"}
    for name, cells in summary.items():
        wins = sum(bool(c["challenger_wins_round"]) for c in cells.values())
        cells["_wins"] = f"{wins}/{len(pools) * len(seeds)}"
    (work / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v["_wins"] for k, v in summary.items()}, indent=2))


if __name__ == "__main__":
    main()
