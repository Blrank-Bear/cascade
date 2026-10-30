"""grid.py with per-step logs: every duel.py call tees its stdout/stderr to WORK/logs/.

Same arguments as grid.py. On failure the log tail is printed before re-raising,
so a failed train/score/judge step is never silent. WORK/logs/current.json names
the step in flight (read by tools/dashboard).

    python grid_logged.py ARMS.json --chain-toml CFG --work DIR [grid.py options]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grid  # noqa: E402

TAIL_LINES = 40


def work_dir_from_argv(argv: list[str]) -> Path:
    return Path(argv[argv.index("--work") + 1]).resolve()


def step_name(args: tuple) -> str:
    """'train-base', 'score-hist55__POOL__seed', 'judge-hist55__POOL__seed'."""
    cmd, target = str(args[0]), Path(str(args[1]))
    if cmd == "judge":
        target = Path(str(args[2]))
    return f"{cmd}-{target.stem if cmd != 'train' else target.name}"


def write_current(logs: Path, step: str | None, log: Path | None) -> None:
    body = {"step": step, "log": str(log) if log else None, "started": time.time() if step else None}
    (logs / "current.json").write_text(json.dumps(body) + "\n")


def logged_run_duel(logs: Path):
    def run(*args) -> dict:
        step = step_name(args)
        log = logs / f"{step}.log"
        write_current(logs, step, log)
        with log.open("w") as fh:
            proc = subprocess.run([sys.executable, str(grid.DUEL), *map(str, args)],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            fh.write(proc.stdout)
        write_current(logs, None, None)
        if proc.returncode != 0:
            print("\n".join(proc.stdout.splitlines()[-TAIL_LINES:]), file=sys.stderr)
            raise subprocess.CalledProcessError(proc.returncode, step)
        out = proc.stdout
        start = out.rfind("\n{\n")
        return json.loads(out[start + 1:] if start >= 0 else out[out.index("{"):])
    return run


def main() -> None:
    logs = work_dir_from_argv(sys.argv) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    grid.run_duel = logged_run_duel(logs)
    grid.main()


if __name__ == "__main__":
    main()
