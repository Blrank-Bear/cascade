"""Data collection for the ops dashboard. Pure stdlib; every function does one thing.

Four groups, each producing one JSON-able dict:
  chain   — public round receipts: king, recent verdicts, settlement countdown
  problem — the eval-pool snapshot pinned by the latest settled round + mirror status
  ours    — local grid duels (arm vs base) and CPU proxy results
  host    — GPU / CPU / RAM / disk, running jobs, tmux sessions, newest log tail
Nothing here reads keys or wallets; the only network reads are public URLs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
import urllib.request
from datetime import datetime
from pathlib import Path

RECEIPTS_URL = "https://s3.hippius.com/cascade-manifests/receipts/index.json"
RECEIPT_URL = "https://s3.hippius.com/cascade-manifests/{key}"
HF_SNAPSHOTS_URL = "https://huggingface.co/api/datasets/Tensor-Link/cascade-eval-pool/tree/main/snapshots"
BLOCK_SECONDS = 12.0
ROUNDS_SHOWN = 40
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
JOB_PATTERN = re.compile(r"(duel|grid|grid_logged|transfer|sample|compare|holds)\.py")
GPU_FIELDS = ("name", "utilization.gpu", "memory.used", "memory.total", "temperature.gpu",
              "power.draw", "power.limit", "clocks.sm", "fan.speed")


# ── network helpers ──────────────────────────────────────────────────────────

def http_json(url: str, timeout: float = 30.0):
    req = urllib.request.Request(url, headers={"User-Agent": "cascade-ops-dashboard"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── chain: public receipts ───────────────────────────────────────────────────

def fetch_receipts() -> dict:
    return http_json(RECEIPTS_URL, timeout=60)


def scored_rounds(index: dict) -> list[dict]:
    """One row per settled round (the last scored receipt per epoch block wins)."""
    by_block: dict[int, dict] = {}
    for r in index.get("rounds", []):
        if r.get("status") == "scored" and r.get("king_geomean") is not None:
            by_block[int(r["epoch_start_block"])] = r
    return [by_block[b] for b in sorted(by_block)]


def round_row(r: dict) -> dict:
    return {k: r.get(k) for k in (
        "epoch_start_block", "round_id", "published_at", "king_uid", "king_hotkey", "king_geomean",
        "chal_uid", "chal_geomean", "win_rate", "lcb", "margin", "dethroned", "inconclusive",
        "n_windows", "n_participants", "post_round_king_uid", "sizes", "receipt_key")}


def king_reign(rows: list[dict]) -> int:
    """Consecutive settled rounds (newest backwards) with the same post-round king."""
    if not rows:
        return 0
    king, n = rows[-1].get("post_round_king_uid"), 0
    for r in reversed(rows):
        if r.get("post_round_king_uid") != king:
            break
        n += 1
    return n


def estimated_block(index: dict, now: float) -> int:
    chain = index.get("chain", {})
    as_of = datetime.fromisoformat(chain["as_of"]).timestamp()
    return int(chain["current_block"] + (now - as_of) / BLOCK_SECONDS)


def epoch_countdown(index: dict, now: float) -> dict:
    chain = index.get("chain", {})
    epoch = int(chain.get("epoch_blocks", 900))
    block = estimated_block(index, now)
    next_boundary = (block // epoch + 1) * epoch
    return {"block_est": block, "epoch_blocks": epoch, "next_boundary": next_boundary,
            "seconds_to_boundary": (next_boundary - block) * BLOCK_SECONDS,
            "epoch_progress": (block % epoch) / epoch}


def domain_rows(r: dict) -> list[dict]:
    return [{"domain": d, **v} for d, v in sorted((r.get("per_domain") or {}).items())]


def horizon_rows(r: dict) -> list[dict]:
    cohort = r.get("cohort_per_horizon") or {}
    cells = cohort.get(r.get("chal_hotkey")) or next(iter(cohort.values()), {})
    return [{"horizon": int(h), **v} for h, v in sorted(cells.items(), key=lambda kv: int(kv[0]))]


def chain_section(index: dict, now: float) -> dict:
    rows = scored_rounds(index)
    last = rows[-1] if rows else {}
    return {
        "updated_at": index.get("updated_at"),
        "countdown": epoch_countdown(index, now) if index.get("chain") else None,
        "king": {"uid": last.get("post_round_king_uid"), "hotkey": last.get("king_hotkey"),
                 "geomean": last.get("king_geomean"), "reign_rounds": king_reign(rows),
                 "gen_ref": last.get("king_gen_ref"), "sizes": last.get("sizes")},
        "latest": round_row(last) if last else None,
        "latest_domains": domain_rows(last),
        "latest_horizons": horizon_rows(last),
        "rounds": [round_row(r) for r in rows[-ROUNDS_SHOWN:]],
        "dethrones_total": sum(bool(r.get("dethroned")) for r in rows),
    }


# ── problem: the pool snapshot pinned by the latest settled round ────────────

def fetch_receipt(key: str) -> dict:
    return http_json(RECEIPT_URL.format(key=key), timeout=120)


def pool_pin(receipt: dict) -> dict:
    manifest = receipt.get("manifest", {})
    ctx = receipt.get("eval_context", {})
    key = manifest.get("eval_pool_key") or ctx.get("pool_ref")
    m = re.search(r"block-(\d+)", key or "")
    return {"pool_key": key, "pool_sha256": manifest.get("eval_pool_sha256") or ctx.get("pool_digest"),
            "effective_block": int(m.group(1)) if m else None, "n_windows": ctx.get("n_windows"),
            "round_block": receipt.get("epoch_start_block"), "base_seed": receipt.get("base_seed")}


def fetch_mirror_blocks() -> list[int]:
    names = [e["path"].rsplit("/", 1)[-1] for e in http_json(HF_SNAPSHOTS_URL, timeout=60)
             if e.get("type") == "directory"]
    return sorted(int(n.rsplit("-block-", 1)[1]) for n in names if "-block-" in n)


def local_pools(pools_dir: Path) -> list[dict]:
    out = []
    for p in sorted(pools_dir.glob("*-block-*")):
        out.append({"name": p.name, "block": int(p.name.rsplit("-block-", 1)[1]),
                    "verified": (p / ".verified").is_file()})
    return out


def problem_section(pin: dict | None, mirror: list[int] | None, pools: list[dict], block_est: int | None) -> dict:
    eff = (pin or {}).get("effective_block")
    return {
        "pin": pin,
        "age_hours": ((block_est - eff) * BLOCK_SECONDS / 3600) if eff and block_est else None,
        "on_public_mirror": (eff in mirror) if (eff and mirror is not None) else None,
        "mirror_latest_block": mirror[-1] if mirror else None,
        "local_pools": pools,
        "local_has_pinned": any(p["block"] == eff for p in pools) if eff else False,
        "note": "The active pool is private; snapshots reach the public mirror about 48 h after retirement.",
    }


# ── ours: local grid duels and proxy results ─────────────────────────────────

def grid_dirs(root: Path) -> list[Path]:
    return sorted((p for p in root.glob("grid*") if p.is_dir()), key=lambda p: p.stat().st_mtime)


def grid_progress(work: Path) -> dict:
    arms = sorted(p.name for p in (work / "gen").glob("*")) if (work / "gen").is_dir() else []
    trained = sorted(p.parent.name for p in (work / "ckpt").glob("*/train.json"))
    scores = sorted(p.stem for p in (work / "scores").glob("*.json")) if (work / "scores").is_dir() else []
    current = read_json(work / "logs" / "current.json") or {}
    return {"arms": arms, "trained": trained, "n_scores": len(scores), "current": current}


def train_metrics(work: Path) -> dict:
    out = {}
    for p in (work / "ckpt").glob("*/train.json"):
        d = read_json(p) or {}
        out[p.parent.name] = {k: d.get(k) for k in ("steps", "train_seconds", "tokens", "final_loss",
                                                     "elapsed_seconds", "points") if k in d}
    return out


def summary_rows(summary: dict) -> list[dict]:
    rows = []
    for arm, cells in summary.items():
        judged = {k: v for k, v in cells.items() if not k.startswith("_")}
        rel = [1 - c["chal_geomean"] / c["king_geomean"] for c in judged.values()
               if c.get("king_geomean") and c.get("chal_geomean") is not None]
        rows.append({"arm": arm, "wins": cells.get("_wins"), "cells": judged,
                     "mean_rel_gain": sum(rel) / len(rel) if rel else None})
    return sorted(rows, key=lambda r: -(r["mean_rel_gain"] or -9))


def grid_section(work: Path) -> dict:
    summary = read_json(work / "summary.json")
    return {"name": work.name, "progress": grid_progress(work), "train": train_metrics(work),
            "summary": summary_rows(summary) if summary else None,
            "mtime": (work / "summary.json").stat().st_mtime if summary else None}


def proxy_section(path: Path) -> dict | None:
    return read_json(path)


def ours_section(work_root: Path, proxy_path: Path) -> dict:
    return {"grids": [grid_section(g) for g in grid_dirs(work_root)][::-1],
            "proxy": proxy_section(proxy_path)}


# ── host: GPU, CPU, memory, disk, jobs ───────────────────────────────────────

def run_text(cmd: list[str], timeout: float = 10.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def to_number(v: str):
    try:
        return float(v)
    except ValueError:
        return v.strip()


def gpu_stats() -> list[dict]:
    out = run_text(["nvidia-smi", f"--query-gpu={','.join(GPU_FIELDS)}", "--format=csv,noheader,nounits"])
    return [dict(zip(GPU_FIELDS, map(to_number, line.split(", ")))) for line in out.strip().splitlines()]


def cpu_times() -> tuple[int, int]:
    vals = list(map(int, Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]))
    return sum(vals), vals[3] + vals[4]


def cpu_util(prev: tuple[int, int] | None, cur: tuple[int, int]) -> float | None:
    if not prev or cur[0] == prev[0]:
        return None
    return 100.0 * (1 - (cur[1] - prev[1]) / (cur[0] - prev[0]))


def mem_stats() -> dict:
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.split()[0]) / 1048576
    return {"total_gb": info["MemTotal"], "used_gb": info["MemTotal"] - info["MemAvailable"]}


def disk_stats(path: Path) -> dict:
    u = shutil.disk_usage(path)
    return {"total_gb": u.total / 1e9, "used_gb": u.used / 1e9, "free_gb": u.free / 1e9}


def job_rows() -> list[dict]:
    rows = []
    for line in run_text(["ps", "-eo", "pid=,etimes=,pcpu=,rss=,args="]).splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and JOB_PATTERN.search(parts[4]):
            rows.append({"pid": int(parts[0]), "elapsed_s": int(parts[1]), "cpu_pct": float(parts[2]),
                         "rss_gb": int(parts[3]) / 1048576, "cmd": short_cmd(parts[4])})
    return rows


def short_cmd(args: str) -> str:
    return re.sub(r"/root/work/cascade/|/root/work/upstream/|\.venv/bin/", "", args)[:220]


def tmux_sessions() -> list[str]:
    return [l.split(":", 1)[0] for l in run_text(["tmux", "ls"]).splitlines() if ":" in l]


def newest_log(globs: list[str], root: Path) -> Path | None:
    files = [p for g in globs for p in root.glob(g) if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def log_tail(path: Path | None, n: int = 40) -> dict | None:
    if path is None:
        return None
    with path.open("rb") as fh:
        fh.seek(max(0, path.stat().st_size - 64_000))
        text = fh.read().decode("utf-8", "replace")
    lines = [ANSI.sub("", l).rstrip() for l in text.replace("\r", "\n").splitlines() if l.strip()]
    return {"path": str(path), "mtime": path.stat().st_mtime, "lines": lines[-n:]}


def uptime_s() -> float:
    return float(Path("/proc/uptime").read_text().split()[0])


def host_section(cpu: float | None, root: Path, log_globs: list[str]) -> dict:
    return {"gpus": gpu_stats(), "cpu_pct": cpu, "load": os.getloadavg(), "ncpu": os.cpu_count(),
            "mem": mem_stats(), "disk": disk_stats(root), "uptime_s": uptime_s(),
            "jobs": job_rows(), "tmux": tmux_sessions(), "log": log_tail(newest_log(log_globs, root))}


# ── v2 launch / config ───────────────────────────────────────────────────────

def v2_launch(chain_toml: Path) -> dict:
    v2 = tomllib.loads(chain_toml.read_text()).get("v2", {})
    return {"launch_at_utc": v2.get("launch_at_utc"), "commit_open_at_utc": v2.get("commit_open_at_utc")}


# ── misc ─────────────────────────────────────────────────────────────────────

def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None
