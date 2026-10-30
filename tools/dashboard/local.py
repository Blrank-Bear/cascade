"""Local ops dashboard (runs on the workstation, binds 127.0.0.1 only, no token).

    python local.py --root REPO [--port 8791] [--ssh-host cascade-gpu]

Sections: code (our repo, generator switches, upstream changes, server sync),
leaderboard + chain + problem (public receipts), gpu (the GPU server's own
dashboard state, fetched over SSH). Settings: REPO/.claude-work/session/dashboard_local.json
  {"my_hotkeys": ["5F..."]}   # public hotkey addresses to highlight (never keys)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codestatus  # noqa: E402
import collect  # noqa: E402
import leaderboard  # noqa: E402
import serve  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
REMOTE_ROOT = "/root/work/cascade"
REMOTE_STATE = (f"T=$(cat {REMOTE_ROOT}/.claude-work/session/dashboard_token) && "
                "curl -s -m 8 -H \"Cookie: ops_token=$T\" localhost:1122/api/state")


# ── settings ─────────────────────────────────────────────────────────────────

def load_settings(path: Path) -> dict:
    if not path.is_file():
        path.write_text(json.dumps({"my_hotkeys": []}, indent=1) + "\n")
    return json.loads(path.read_text())


def ssh_cmd(host: str, control_dir: Path) -> list[str]:
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ControlMaster=auto",
            "-o", f"ControlPath={control_dir}/cm-%r@%h-%p", "-o", "ControlPersist=10m", host]


# ── change detection (new, local-only events) ────────────────────────────────

def diff_commits(state: serve.State, old: dict | None, new: dict) -> None:
    if old and old.get("head") != new.get("head") and new.get("commits"):
        c = new["commits"][0]
        state.event("code", f"new commit {c['hash']}: {c['subject']}")


def diff_upstream(state: serve.State, old: dict | None, new: dict) -> None:
    if old and old.get("remote_head") != new.get("remote_head"):
        state.event("upstream", f"upstream {codestatus.UPSTREAM_BRANCH} moved to {new.get('remote_head')} "
                                f"({len(new.get('behind', []))} commits not yet pulled)", level="warn")


def diff_sync(state: serve.State, old: dict | None, new: dict) -> None:
    if old and old.get("n_differ") != new.get("n_differ"):
        level = "warn" if new["n_differ"] else "info"
        state.event("sync", f"server copy: {new['n_differ']} tracked files differ from local", level=level)


def diff_reach(state: serve.State, flags: dict, ok: bool) -> None:
    if flags.get("reach") is not None and flags["reach"] != ok:
        state.event("server", "GPU server reachable again" if ok else "GPU server unreachable",
                    level="info" if ok else "error")
    flags["reach"] = ok


# ── loops ────────────────────────────────────────────────────────────────────

def code_tick(state: serve.State, root: Path) -> None:
    repo = codestatus.repo_section(root)
    diff_commits(state, state.get("repo"), repo)
    state.put("repo", repo)
    state.put("generator", codestatus.generator_section(root / "generator"))


def upstream_tick(state: serve.State, root: Path, cache: dict, every: float) -> None:
    if time.time() - cache.get("t", 0) > every:
        codestatus.upstream_fetch(root / "upstream")
        cache["t"] = time.time()
    up = codestatus.upstream_section(root / "upstream")
    diff_upstream(state, state.get("upstream"), up)
    state.put("upstream", up)


def server_tick(state: serve.State, ssh: list[str], flags: dict) -> None:
    out = subprocess.run([*ssh, REMOTE_STATE], capture_output=True, text=True, timeout=30).stdout
    try:
        remote = json.loads(out)
    except ValueError:
        diff_reach(state, flags, False)
        raise RuntimeError("GPU server dashboard not reachable over SSH")
    diff_reach(state, flags, True)
    state.put("server", {k: remote.get(k) for k in ("now", "history", "events", "errors", "updated")}
              | {"host": remote["sections"].get("host"), "ours": remote["sections"].get("ours")})


def sync_tick(state: serve.State, root: Path, ssh: list[str]) -> None:
    up = state.get("upstream") or {}
    sync = codestatus.sync_section(root, codestatus.server_digests(ssh, REMOTE_ROOT), up.get("head", ""))
    diff_sync(state, state.get("sync"), sync)
    state.put("sync", sync)


def chain_tick(state: serve.State, root: Path, cache: dict, mine: set[str]) -> None:
    index = collect.fetch_receipts()
    chain = collect.chain_section(index, time.time())
    serve.diff_chain(state, state.get("chain"), chain)
    state.put("chain", chain)
    key = (chain.get("latest") or {}).get("receipt_key")
    if key and key != cache.get("receipt_key"):
        receipt = collect.fetch_receipt(key)
        pin = collect.pool_pin(receipt)
        serve.diff_pin(state, cache.get("pin"), pin)
        cache.update(receipt_key=key, pin=pin, receipt_lite={k: receipt.get(k) for k in
                     ("participants", "weights", "entry_scores", "epoch_start_block")})
        cache["receipt_lite"]["entry_scores"] = [{"hotkey": e.get("hotkey"), "role": e.get("role")}
                                                 for e in receipt.get("entry_scores", [])]
    rows = collect.scored_rounds(index)
    state.put("leaderboard", leaderboard.leaderboard(rows, cache.get("receipt_lite", {}), mine))
    if time.time() - cache.get("mirror_t", 0) > serve.MIRROR_EVERY_S:
        cache.update(mirror=collect.fetch_mirror_blocks(), mirror_t=time.time())
    block = (chain.get("countdown") or {}).get("block_est")
    state.put("problem", collect.problem_section(cache.get("pin"), cache.get("mirror"),
                                                 collect.local_pools(root / ".claude-work/data/pools"), block))


def start_local_loops(state: serve.State, root: Path, ssh: list[str], mine: set[str]) -> None:
    flags: dict = {}
    up_cache: dict = {}
    chain_cache: dict = {}
    jobs = (("code", 10, lambda: code_tick(state, root)),
            ("upstream", 30, lambda: upstream_tick(state, root, up_cache, 600)),
            ("server", 6, lambda: server_tick(state, ssh, flags)),
            ("sync", 60, lambda: sync_tick(state, root, ssh)),
            ("chain", 120, lambda: chain_tick(state, root, chain_cache, mine)))
    for name, period, fn in jobs:
        threading.Thread(target=serve.loop, args=(state, name, period, fn), daemon=True).start()


# ── HTTP (localhost only) ────────────────────────────────────────────────────

def make_local_handler(state: serve.State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send_body(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self.send_body(200, (STATIC / "local.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/state":
                body = json.dumps(serve.finite(state.snapshot()), default=str)
                return self.send_body(200, body.encode(), "application/json")
            return self.send_body(404, b"not found", "text/plain")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--ssh-host", default="cascade-gpu")
    args = ap.parse_args()
    root = args.root.resolve()
    session = root / ".claude-work" / "session"
    (session / "dashboard_local").mkdir(parents=True, exist_ok=True)
    settings = load_settings(session / "dashboard_local.json")
    state = serve.State(session / "dashboard_local" / "events.jsonl")
    try:
        state.put("v2", collect.v2_launch(root / "upstream" / "chain.toml"))
    except (OSError, ValueError) as e:
        state.fail("v2", str(e))
    state.event("dashboard", "local dashboard started")
    ssh = ssh_cmd(args.ssh_host, Path.home() / ".ssh")  # control sockets cannot live on /mnt (drvfs)
    start_local_loops(state, root, ssh, set(settings.get("my_hotkeys", [])))
    ThreadingHTTPServer(("127.0.0.1", args.port), make_local_handler(state)).serve_forever()


if __name__ == "__main__":
    main()
