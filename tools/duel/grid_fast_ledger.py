"""grid_fast.py plus ledger metadata: each duel step also writes WORK/logs/<step>.meta.json.

The metadata is captured at the moment the step runs (a later grid run re-copies gen/<arm>/):
generator.py sha256, the arm's switch files, the server-side git HEAD of the repo copy (if any),
the full argv, start/end time and exit code. Same arguments as grid.py.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import grid  # noqa: E402
import grid_logged  # noqa: E402

grid.DUEL = HERE / "duel_fast.py"
GEN_SKIP = {"config.json"}


def gen_meta(gen_dir: Path) -> dict:
    src = gen_dir / "generator.py"
    return {"generator_sha256": hashlib.sha256(src.read_bytes()).hexdigest() if src.is_file() else None,
            "switches": {p.name: json.loads(p.read_text()) for p in sorted(gen_dir.glob("*.json")) if p.name not in GEN_SKIP}}


def repo_head() -> str | None:
    out = subprocess.run(["git", "-C", str(HERE.parents[1]), "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip() or None


def ledger_run_duel(logs: Path, inner):
    def run(*args) -> dict:
        step = grid_logged.step_name(args)
        meta = {"step": step, "argv": [str(a) for a in args], "started": time.time(), "repo_head": repo_head()}
        if str(args[0]) == "train":
            meta.update(gen_meta(Path(str(args[1]))))
        try:
            out = inner(*args)
            meta["exit"] = 0
            return out
        except Exception as e:
            meta["exit"] = getattr(e, "returncode", 1)
            raise
        finally:
            meta["ended"] = time.time()
            (logs / f"{step}.meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return run


def main() -> None:
    logs = grid_logged.work_dir_from_argv(sys.argv) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    grid.run_duel = ledger_run_duel(logs, grid_logged.logged_run_duel(logs))
    grid.main()


if __name__ == "__main__":
    main()
