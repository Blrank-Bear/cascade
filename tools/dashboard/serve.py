"""Ops dashboard server: background collectors + a token-protected web UI.

    python serve.py --root REPO [--port 1122] [--host 0.0.0.0] [--fast 5] [--slow 120]

Open http://HOST:PORT/?token=TOKEN once; the token is then kept in an HttpOnly
cookie. The token lives in REPO/.claude-work/session/dashboard_token (created on
first start, git-ignored). Audit events append to
REPO/.claude-work/session/dashboard/events.jsonl.
"""
from __future__ import annotations

import argparse
import hmac
import json
import secrets
import sys
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
HISTORY_POINTS = 720          # 1 h at the default 5 s tick
EVENTS_KEPT = 300
MIRROR_EVERY_S = 600
LOG_GLOBS = [".claude-work/tmp/*.log", ".claude-work/grid*/logs/*.log"]


# ── shared state ─────────────────────────────────────────────────────────────

class State:
    def __init__(self, events_path: Path):
        self.lock = threading.Lock()
        self.data: dict = {"sections": {}, "errors": {}, "updated": {}}
        self.history: deque = deque(maxlen=HISTORY_POINTS)
        self.events: deque = deque(maxlen=EVENTS_KEPT)
        self.events_path = events_path
        self.load_events()

    def load_events(self) -> None:
        if self.events_path.is_file():
            for line in self.events_path.read_text().splitlines()[-EVENTS_KEPT:]:
                try:
                    self.events.append(json.loads(line))
                except ValueError:
                    pass

    def put(self, name: str, value) -> None:
        with self.lock:
            self.data["sections"][name] = value
            self.data["updated"][name] = time.time()
            self.data["errors"].pop(name, None)

    def fail(self, name: str, err: str) -> None:
        with self.lock:
            self.data["errors"][name] = err

    def get(self, name: str):
        with self.lock:
            return self.data["sections"].get(name)

    def event(self, kind: str, text: str, level: str = "info") -> None:
        ev = {"t": time.time(), "kind": kind, "level": level, "text": text}
        with self.lock:
            self.events.append(ev)
        with self.events_path.open("a") as fh:
            fh.write(json.dumps(ev) + "\n")

    def snapshot(self) -> dict:
        with self.lock:
            return {**self.data, "now": time.time(), "history": list(self.history),
                    "events": list(self.events)[::-1]}


# ── change detection → audit events ──────────────────────────────────────────

def diff_jobs(state: State, old: list[dict] | None, new: list[dict]) -> None:
    old_ids = {j["pid"]: j for j in old or []}
    new_ids = {j["pid"]: j for j in new}
    if old is None:
        return
    for pid in new_ids.keys() - old_ids.keys():
        state.event("job", f"started pid {pid}: {new_ids[pid]['cmd'][:120]}")
    for pid in old_ids.keys() - new_ids.keys():
        state.event("job", f"ended pid {pid} after {old_ids[pid]['elapsed_s'] // 60} min: "
                           f"{old_ids[pid]['cmd'][:120]}")


def diff_chain(state: State, old: dict | None, new: dict) -> None:
    if not old or not new.get("latest") or not old.get("latest"):
        return
    a, b = old["latest"], new["latest"]
    if a["epoch_start_block"] != b["epoch_start_block"]:
        verdict = "DETHRONED" if b.get("dethroned") else "king held"
        state.event("round", f"round {b['epoch_start_block']} settled: {verdict}; king uid "
                             f"{b.get('post_round_king_uid')} geomean {b.get('king_geomean'):.4f}")
    if old["king"].get("uid") != new["king"].get("uid"):
        state.event("king", f"new king: uid {new['king'].get('uid')}", level="warn")


def diff_pin(state: State, old: dict | None, new: dict) -> None:
    if old and old.get("pool_key") != new.get("pool_key"):
        state.event("problem", f"eval pool changed: {old.get('pool_key')} -> {new.get('pool_key')}", level="warn")


def check_gpu(state: State, host: dict, flags: dict) -> None:
    for g in host.get("gpus", []):
        hot = isinstance(g.get("temperature.gpu"), float) and g["temperature.gpu"] >= 83
        if hot and not flags.get("hot"):
            state.event("gpu", f"GPU temperature {g['temperature.gpu']:.0f} C", level="warn")
        flags["hot"] = hot
    if not host.get("gpus") and not flags.get("nogpu"):
        state.event("gpu", "nvidia-smi returned no GPU", level="error")
    flags["nogpu"] = not host.get("gpus")


# ── collector loops ──────────────────────────────────────────────────────────

def history_point(host: dict) -> dict:
    g = (host.get("gpus") or [{}])[0]
    return {"t": time.time(), "gpu": g.get("utilization.gpu"), "mem": g.get("memory.used"),
            "temp": g.get("temperature.gpu"), "power": g.get("power.draw"), "cpu": host.get("cpu_pct")}


def fast_tick(state: State, root: Path, prev_cpu, flags: dict):
    cur_cpu = collect.cpu_times()
    host = collect.host_section(collect.cpu_util(prev_cpu, cur_cpu), root, LOG_GLOBS)
    diff_jobs(state, (state.get("host") or {}).get("jobs") if state.get("host") else None, host["jobs"])
    check_gpu(state, host, flags)
    state.put("host", host)
    with state.lock:
        state.history.append(history_point(host))
    state.put("ours", collect.ours_section(root / ".claude-work", root / ".claude-work/tmp/proxy/transfer_chain4.json"))
    return cur_cpu


def slow_tick(state: State, root: Path, cache: dict) -> None:
    index = collect.fetch_receipts()
    chain = collect.chain_section(index, time.time())
    diff_chain(state, state.get("chain"), chain)
    state.put("chain", chain)
    key = (chain.get("latest") or {}).get("receipt_key")
    if key and key != cache.get("receipt_key"):
        pin = collect.pool_pin(collect.fetch_receipt(key))
        diff_pin(state, cache.get("pin"), pin)
        cache.update(receipt_key=key, pin=pin)
    if time.time() - cache.get("mirror_t", 0) > MIRROR_EVERY_S:
        cache.update(mirror=collect.fetch_mirror_blocks(), mirror_t=time.time())
    block = (chain.get("countdown") or {}).get("block_est")
    state.put("problem", collect.problem_section(cache.get("pin"), cache.get("mirror"),
                                                 collect.local_pools(root / ".claude-work/data/pools"), block))


def loop(state: State, name: str, period: float, fn) -> None:
    while True:
        try:
            fn()
        except Exception as e:  # keep the loop alive; surface the error in the UI
            state.fail(name, f"{type(e).__name__}: {e}")
            traceback.print_exc()
        time.sleep(period)


def start_loops(state: State, root: Path, fast: float, slow: float) -> None:
    flags: dict = {}
    cpu = [collect.cpu_times()]
    cache: dict = {}

    def fast_fn():
        cpu[0] = fast_tick(state, root, cpu[0], flags)

    for name, period, fn in (("fast", fast, fast_fn), ("slow", slow, lambda: slow_tick(state, root, cache))):
        threading.Thread(target=loop, args=(state, name, period, fn), daemon=True).start()


# ── auth ─────────────────────────────────────────────────────────────────────

def load_token(path: Path) -> str:
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(24) + "\n")
        path.chmod(0o600)
    return path.read_text().strip()


def cookie_token(header: str | None) -> str | None:
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "ops_token":
            return v
    return None


# ── HTTP ─────────────────────────────────────────────────────────────────────

def finite(o):
    """NaN/inf -> None, recursively, so the payload is strict JSON."""
    if isinstance(o, float):
        return o if o == o and abs(o) != float("inf") else None
    if isinstance(o, dict):
        return {k: finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [finite(v) for v in o]
    return o


def make_handler(state: State, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def send_body(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def authed(self) -> bool:
            got = cookie_token(self.headers.get("Cookie"))
            return bool(got) and hmac.compare_digest(got, token)

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query).get("token", [None])[0]
            if q is not None:
                if hmac.compare_digest(q, token):
                    cookie = f"ops_token={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000"
                    return self.send_body(302, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})
                return self.send_body(401, (STATIC / "login.html").read_bytes(), "text/html; charset=utf-8")
            if not self.authed():
                return self.send_body(401, (STATIC / "login.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/":
                return self.send_body(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/state":
                body = json.dumps(finite(state.snapshot()), default=str)
                return self.send_body(200, body.encode(), "application/json")
            return self.send_body(404, b"not found", "text/plain")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=1122)
    ap.add_argument("--fast", type=float, default=5.0)
    ap.add_argument("--slow", type=float, default=120.0)
    args = ap.parse_args()
    root = args.root.resolve()
    session = root / ".claude-work" / "session"
    token = load_token(session / "dashboard_token")
    (session / "dashboard").mkdir(parents=True, exist_ok=True)
    state = State(session / "dashboard" / "events.jsonl")
    try:
        state.put("v2", collect.v2_launch(root / "upstream" / "chain.toml"))
    except (OSError, ValueError) as e:
        state.fail("v2", str(e))
    state.event("dashboard", "dashboard started")
    start_loops(state, root, args.fast, args.slow)
    ThreadingHTTPServer((args.host, args.port), make_handler(state, token)).serve_forever()


if __name__ == "__main__":
    main()
