"""Projected on-chain round metric for our code, from the experiment ledger (ledger/analysis.json).

We have no settled on-chain round yet, so "our score" is an estimate: for each settled round,
    projected = king_geomean * (1 - gain)
where gain is our best single feature's mean measured gain vs the king-equivalent base generator in
local equal-step GPU duels (28m screening model, not the 120M contract model). The section carries
the stats behind it so the page can say exactly what the number is.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

MIN_SEEDS = 3


def load_results(path: Path) -> list[dict]:
    return json.loads(path.read_text()).get("results", [])


def eligible(results: list[dict]) -> list[dict]:
    """Features measured on enough seeds and not rejected."""
    return [r for r in results if r["stats"]["n"] >= MIN_SEEDS and r.get("verdict") != "REJECT"]


def pick_best(results: list[dict]) -> dict | None:
    pool = eligible(results)
    return max(pool, key=lambda r: r["stats"]["mean"]) if pool else None


def standard_error(stats: dict) -> float | None:
    n, sd = stats.get("n") or 0, stats.get("sd")
    return sd / math.sqrt(n) if n > 1 and sd is not None else None


def summarise(r: dict) -> dict:
    s = r["stats"]
    return {"arm": r["arm_names"][0], "feature": r["feature"], "verdict": r.get("verdict"),
            "n": s["n"], "mean": s["mean"], "sd": s.get("sd"), "se": standard_error(s), "t": s.get("t"),
            "min": s.get("min"), "max": s.get("max"), "horizon_means": r.get("horizon_means")}


def projection_section(analysis_path: Path) -> dict:
    results = load_results(analysis_path)
    best = pick_best(results)
    return {"best": summarise(best) if best else None,
            "adopted": [summarise(r) for r in results if r.get("verdict") == "ADOPT-CANDIDATE"],
            "n_features": len(results), "basis": "local 28m equal-step GPU duels vs king-equivalent base",
            "source": str(analysis_path.name), "mtime": analysis_path.stat().st_mtime}
