"""Local ops dashboard v3: everything local_v2.py serves, plus state section "ours_proj"
(projected on-chain score for our code, from ledger/analysis.json via ours_projection.py).

    python local_v3.py --root REPO [--port 8791] [--ssh-host cascade-gpu] [--v2-every 180] [--proj-every 60]
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
import local_v2  # noqa: E402
import ours_projection  # noqa: E402
import serve  # noqa: E402


def proj_tick(state: serve.State, root: Path) -> None:
    state.put("ours_proj", ours_projection.projection_section(root / "ledger" / "analysis.json"))


def start_proj_loop(state: serve.State, root: Path, every: float) -> None:
    threading.Thread(target=serve.loop, args=(state, "ours_proj", every, lambda: proj_tick(state, root)), daemon=True).start()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--ssh-host", default="cascade-gpu")
    ap.add_argument("--v2-every", type=float, default=180.0)
    ap.add_argument("--proj-every", type=float, default=60.0)
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
    state.event("dashboard", "local dashboard (v2 panel + our projected score) started")
    ssh = local.ssh_cmd(args.ssh_host, Path.home() / ".ssh")
    local.start_local_loops(state, root, ssh, set(settings.get("my_hotkeys", [])))
    local_v2.start_v2_loop(state, root, args.v2_every)
    start_proj_loop(state, root, args.proj_every)
    ThreadingHTTPServer(("127.0.0.1", args.port), local.make_local_handler(state)).serve_forever()


if __name__ == "__main__":
    main()
