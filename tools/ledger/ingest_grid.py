"""Turn one synced GPU grid snapshot into an experiment-ledger record (ledger/experiments.jsonl).

    python ingest_grid.py SNAPSHOT_DIR --grid NAME --seed S --hours H --config CFG_NAME [--note TEXT]

SNAPSHOT_DIR is .claude-work/grids/<grid>/<stamp>/ (from tools/ledger/sync_grid.sh). The record holds,
per arm: switch files, generator sha256, training steps/seconds, per-cell verdicts and per-horizon /
per-domain log ratios vs the reference arm; plus validity checks:
  equal_steps     every arm trained the same number of steps
  same_generator  every arm ran the same generator.py bytes
  single_feature  every non-reference arm differs from the reference by exactly one switch file
  no_failures     the grid log ends in EXIT 0
Invalid records stay in the ledger (with reasons) but are excluded by tools/ledger/analyze.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ledger" / "experiments.jsonl"
GEN_SKIP = {"config.json"}
sys.path.insert(0, str(ROOT / "tools" / "duel"))
import breakdown_scores as B  # noqa: E402


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git_head() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def arm_switches(gen_dir: Path) -> dict:
    return {p.name: json.loads(p.read_text()) for p in sorted(gen_dir.glob("*.json")) if p.name not in GEN_SKIP}


def arm_training(ckpt_dir: Path) -> dict:
    t = json.loads((ckpt_dir / "train.json").read_text()) if (ckpt_dir / "train.json").is_file() else {}
    return {"steps": (t.get("n_series") or 0) // 16 if t else None, "n_series": t.get("n_series"),
            "train_seconds": t.get("train_seconds"), "corpus_digest": t.get("corpus_digest")}


def cell_results(summary: dict, arm: str) -> dict:
    cells = {k: v for k, v in (summary.get(arm) or {}).items() if not k.startswith("_")}
    out = {}
    for k, c in cells.items():
        out[k] = {"gain": 1 - c["chal_geomean"] / c["king_geomean"] if c.get("king_geomean") else None,
                  "lcb": c.get("lcb"), "win": c.get("challenger_wins_round"), "n_windows": c.get("n_windows"),
                  "per_horizon": {h: v.get("rel_improvement") for h, v in (c.get("per_horizon") or {}).items()}}
    return out


def breakdown(work: Path, arm: str, ref: str) -> dict:
    by = {"domain": defaultdict(list), "horizon": defaultdict(list)}
    for ra, rb in B.paired_rows(work, arm, ref):
        v = (B.log_ratio(ra.get("mase"), rb.get("mase"), B.FLOOR_MASE),
             B.log_ratio(B.window_wql(ra), B.window_wql(rb), B.FLOOR_WQL))
        by["domain"][ra.get("domain", "?")].append(v)
        by["horizon"][str(ra.get("horizon", "?"))].append(v)
    return {k: B.summarise(g) for k, g in by.items()}


def single_feature(sw: dict, ref_sw: dict) -> int:
    """Number of switch files that differ from the reference."""
    keys = set(sw) | set(ref_sw)
    return sum(1 for k in keys if sw.get(k) != ref_sw.get(k))


def grid_exit(snapshot: Path, grid: str) -> list[str]:
    exits = []
    for log in snapshot.glob(f"{grid}*.log"):
        exits += [l.strip() for l in log.read_text(errors="replace").splitlines() if l.startswith("EXIT")]
    return exits


def build_record(snapshot: Path, grid: str, ref: str, meta: dict) -> dict:
    work = snapshot / grid
    arms = sorted(p.name for p in (work / "gen").iterdir() if p.is_dir())
    summary = json.loads((work / "summary.json").read_text()) if (work / "summary.json").is_file() else {}
    rows = {}
    for a in arms:
        rows[a] = {"switches": arm_switches(work / "gen" / a),
                   "generator_sha256": sha256(work / "gen" / a / "generator.py"),
                   "training": arm_training(work / "ckpt" / a)}
    ref_sw = rows.get(ref, {}).get("switches", {})
    for a in arms:
        rows[a]["n_features_vs_ref"] = single_feature(rows[a]["switches"], ref_sw)
        if a != ref and a in summary:
            rows[a]["cells"] = cell_results(summary, a)
            rows[a]["breakdown"] = breakdown(work, a, ref)
    judged = [a for a in arms if a != ref and a in summary]
    steps = {rows[a]["training"]["steps"] for a in arms if rows[a]["training"]["steps"]}
    exits = grid_exit(snapshot, grid)
    shas = {rows[a]["generator_sha256"] for a in arms}
    equivalent = [p for p in meta.get("equivalent_generators", []) if p]
    same = len(shas) == 1 or (bool(equivalent) and all(any(s.startswith(p) for p in equivalent) for s in shas))
    checks = {
        "equal_steps": len(steps) == 1,
        "same_generator": same,
        "no_failures": bool(exits) and all(e == "EXIT 0" for e in exits),
    }
    for a in judged:  # per-arm: only single-feature arms are attributable
        rows[a]["single_feature"] = rows[a]["n_features_vs_ref"] == 1
    return {"id": f"{grid}@{snapshot.name}", "kind": "gpu_grid", "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_head": git_head(), "grid": grid, "snapshot": str(snapshot.relative_to(ROOT)), "reference": ref,
            "budget": meta, "steps": sorted(steps), "checks": checks, "valid": all(checks.values()),
            "invalid_reasons": [k for k, ok in checks.items() if not ok], "judged_arms": judged,
            "single_feature_arms": [a for a in judged if rows[a]["single_feature"]], "arms": rows}


def append(record: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=lambda o: None if isinstance(o, float) and math.isnan(o) else o) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--grid", required=True)
    ap.add_argument("--ref", default="base")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--hours", type=float, required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--equivalent-generator", action="append", default=[],
                    help="sha256 prefix of a generator verified output-identical to the others (golden "
                         "digests); repeat for each. Recorded as a waiver on the same_generator check.")
    ap.add_argument("--waiver-reason", default="")
    a = ap.parse_args()
    meta = {"train_seed": a.seed, "hours": a.hours, "config": a.config, "note": a.note}
    if a.equivalent_generator:
        meta.update(equivalent_generators=a.equivalent_generator, waiver_reason=a.waiver_reason)
    rec = build_record(a.snapshot.resolve(), a.grid, a.ref, meta)
    append(rec)
    print(json.dumps({k: rec[k] for k in ("id", "steps", "checks", "valid", "invalid_reasons", "judged_arms")}, indent=1))


if __name__ == "__main__":
    main()
