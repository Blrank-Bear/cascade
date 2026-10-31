"""Local ops dashboard + v2 submissions panel (wraps local.py; adds one collector loop).

    python local_v2.py --root REPO [--port 8791] [--ssh-host cascade-gpu] [--v2-every 180]

Everything local.py serves, plus state section "v2" from `cascade status --json`
(tools/dashboard/v2status.py) and audit events: new v2 submissions, queue/generation
phase changes, and the first v2 king being set.
"""
from __future__ import annotations

import argparse
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402
import local  # noqa: E402
import serve  # noqa: E402
import v2status  # noqa: E402


def diff_v2(state: serve.State, old: dict | None, new: dict) -> None:
    if not old:
        return
    if not old["king"].get("pointer") and new["king"].get("pointer"):
        state.event("king", f"FIRST v2 KING set: {new['king']['pointer']}", level="warn")
    before = {r["hotkey"]: r for r in old.get("submissions", [])}
    for r in new.get("submissions", []):
        o = before.get(r["hotkey"])
        if o is None:
            state.event("v2", f"new v2 submission: uid {r['uid']} ({r['gen_ref']})")
            continue
        if (o["queue_phase"], o["gen_stage"]) != (r["queue_phase"], r["gen_stage"]):
            state.event("v2", f"uid {r['uid']}: {o['queue_phase']}/{o['gen_stage']} -> {r['queue_phase']}/{r['gen_stage']}")


def v2_tick(state: serve.State, root: Path) -> None:
    data = v2status.fetch_status(root / ".claude-work" / "venv" / "bin" / "cascade", root / "upstream")
    section = v2status.v2_section(data)
    diff_v2(state, state.get("v2live"), section)
    state.put("v2live", section)


def start_v2_loop(state: serve.State, root: Path, every: float) -> None:
    threading.Thread(target=serve.loop, args=(state, "v2live", every, lambda: v2_tick(state, root)), daemon=True).start()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--ssh-host", default="cascade-gpu")
    ap.add_argument("--v2-every", type=float, default=180.0)
    args = ap.parse_args()
    root = args.root.resolve()
    session = root / ".claude-work" / "session"
    (session / "dashboard_local").mkdir(parents=True, exist_ok=True)
    settings = local.load_settings(session / "dashboard_local.json")
    state = serve.State(session / "dashboard_local" / "events.jsonl")
    try:
        state.put("v2", collect.v2_launch(root / "upstream" / "chain.toml"))
    except (OSError, ValueError) as e:
        state.fail("v2", str(e))
    state.event("dashboard", "local dashboard (with v2 panel) started")
    ssh = local.ssh_cmd(args.ssh_host, Path.home() / ".ssh")
    local.start_local_loops(state, root, ssh, set(settings.get("my_hotkeys", [])))
    start_v2_loop(state, root, args.v2_every)
    ThreadingHTTPServer(("127.0.0.1", args.port), local.make_local_handler(state)).serve_forever()


if __name__ == "__main__":
    main()
