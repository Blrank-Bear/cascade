"""Run upstream's own v2 bench gate (cascade.eval.bench_gate.evaluate_bench_gate) on two reports.

    python bench_gate_check.py ARM.json REF.json [--rule avg_noninf_winrate] [--alpha 0.05] [--B 2000]

ARM plays the challenger, REF the king. Upstream's v2 rule needs all four suites (GIFT-Eval,
BOOM, TIME, FEV); with FEV missing it reports the gate as not computable, so the script also
re-runs the same rule restricted to the suites present (marked "partial: FEV missing").
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

from cascade.eval import bench_gate as G
from cascade.eval.benchmarks import extract_bench_scores, item_rows_from_report


def as_dict(res) -> dict:
    d = asdict(res) if is_dataclass(res) else dict(res)
    return {k: v for k, v in d.items() if not callable(v)}


def run(arm: dict, ref: dict, rule: str, alpha: float, B: int, seed: str) -> dict:
    return as_dict(G.evaluate_bench_gate(item_rows_from_report(ref), item_rows_from_report(arm),
                                         extract_bench_scores(ref), extract_bench_scores(arm),
                                         alpha=alpha, B=B, seed=seed, rule=rule))


def partial(arm: dict, ref: dict, rule: str, alpha: float, B: int, seed: str) -> dict:
    present = [k for k, v in (item_rows_from_report(arm) or {}).items() if v.get("status") == "ok" and v.get("rows")]
    old = G.SUITES_V2
    try:
        G.SUITES_V2 = tuple(s for s in old if s in present)
        out = run(arm, ref, rule, alpha, B, seed)
    finally:
        G.SUITES_V2 = old
    out["partial_suites"] = list(G.SUITES_V2 if False else [s for s in old if s in present])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", type=Path)
    ap.add_argument("ref", type=Path)
    ap.add_argument("--rule", default=G.RULE_V2)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--B", type=int, default=2000)
    ap.add_argument("--seed", default="ledger")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    arm, ref = json.loads(a.arm.read_text()), json.loads(a.ref.read_text())
    report = {"rule": a.rule, "full": run(arm, ref, a.rule, a.alpha, a.B, a.seed),
              "partial_without_missing_suites": partial(arm, ref, a.rule, a.alpha, a.B, a.seed)}
    text = json.dumps(report, indent=1, default=str)
    if a.out:
        a.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
