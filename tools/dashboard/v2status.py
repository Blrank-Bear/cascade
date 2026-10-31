"""v2 era status for the dashboard, from upstream's read-only `cascade status --json`.

Produces: go-live state, v2 king pointer, warm-start mode, readiness, queue and
generation stage counts, and one row per on-chain Lane A submission (commit time,
queue phase, generation stage/progress, last error). No wallet or key is involved.
"""
from __future__ import annotations

import collections
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

BLOCK_SECONDS = 12.0


def fetch_status(cascade_bin: Path, cwd: Path, timeout: float = 240.0) -> dict:
    out = subprocess.run([str(cascade_bin), "status", "--json"], cwd=str(cwd), capture_output=True,
                         text=True, timeout=timeout).stdout
    doc = json.loads(out)
    if not doc.get("ok", True) and "data" not in doc:
        raise RuntimeError(f"cascade status failed: {doc.get('error')}")
    return doc["data"]


def block_time(as_of: datetime, now_block: int, block: int) -> str:
    return (as_of - timedelta(seconds=BLOCK_SECONDS * (now_block - block))).isoformat(timespec="minutes")


def latest_generation(progress: list[dict]) -> dict[str, dict]:
    """Newest generation-progress record per hotkey."""
    out: dict[str, dict] = {}
    for g in sorted(progress, key=lambda g: g.get("as_of", "")):
        out[g.get("hotkey", "")] = g
    return out


def queue_by_hotkey(entries: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in sorted(entries, key=lambda e: e.get("last_active") or 0):
        out[e.get("hotkey", "")] = e
    return out


def submission_row(s: dict, q: dict, g: dict, as_of: datetime, now_block: int) -> dict:
    return {
        "uid": s.get("uid"), "hotkey": s.get("hotkey"), "commit_block": s.get("commit_block"),
        "committed_at": block_time(as_of, now_block, int(s.get("commit_block") or now_block)),
        "gen_ref": (s.get("gen_ref") or "").split("@sha256:")[-1][:12],
        "queue_status": q.get("status"), "queue_phase": q.get("phase"), "attempts": q.get("attempts"),
        "last_error": q.get("last_error_class") or q.get("phase_reason") or "",
        "label": q.get("label") or "",
        "gen_stage": g.get("stage"), "gen_percent": g.get("percent"),
        "gen_points": g.get("points"), "gen_elapsed_s": g.get("elapsed_seconds"),
        "gen_as_of": g.get("as_of"),
    }


def v2_section(data: dict) -> dict:
    chain = data.get("chain", {})
    as_of = datetime.fromisoformat(chain["as_of"])
    now_block = int(chain["current_block"])
    queue_entries = (data.get("queues", {}).get("a") or {}).get("entries", [])
    progress = data.get("generation_progress") or []
    q, g = queue_by_hotkey(queue_entries), latest_generation(progress)
    subs = chain.get("submissions") or []
    rows = [submission_row(s, q.get(s.get("hotkey"), {}), g.get(s.get("hotkey"), {}), as_of, now_block) for s in subs]
    rows.sort(key=lambda r: -(r["commit_block"] or 0))
    golive, king, warm = data.get("golive", {}), data.get("king", {}), data.get("warm_start", {})
    return {
        "as_of": chain.get("as_of"), "block": now_block,
        "golive": {k: golive.get(k) for k in ("state", "from_block", "commit_open_at_utc", "admission_state")},
        "king": {"era": king.get("era"), "pointer": king.get("pointer") or warm.get("pointer") or ""},
        "warm_start_mode": warm.get("mode"), "ready_for_training": data.get("ready_for_training"),
        "model": {k: (data.get("model") or {}).get(k) for k in ("name", "preset", "active_params", "total_params")},
        "queue_counts": dict(collections.Counter(f"{e.get('status')}/{e.get('phase')}" for e in queue_entries)),
        "gen_counts": dict(collections.Counter(r["gen_stage"] or "none" for r in rows)),
        "rounds_generating": sorted({p.get("round_id", "")[:20] for p in progress}),
        "submissions": rows,
    }
