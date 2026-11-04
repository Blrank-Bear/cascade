"""grid_fast_ledger.py with an exclusive GPU lock around train steps, for parallel lanes.

A 28m train step needs ~16 GB of the 24 GB card, so two cannot overlap; score steps
are CPU-bound (~1.7 GB GPU). Each train step takes flock(LOCK) first; score/judge steps
take a shared SCORE_LOCK, so one lane scores while another trains. Locks are released on exit/crash.
A failed step (e.g. CUDA OOM from the overlap) is retried once in exclusive mode: the train lock
plus an exclusive score lock, i.e. alone on the GPU.

    python grid_gpulock.py ARMS.json --chain-toml CFG --work DIR [grid.py options]
    env GPU_LOCK (default /root/work/cascade/.claude-work/gpu_train.lock)
"""
from __future__ import annotations

import fcntl
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import grid  # noqa: E402
import grid_fast_ledger  # noqa: E402
import grid_logged  # noqa: E402

LOCK = Path(os.environ.get("GPU_LOCK", "/root/work/cascade/.claude-work/gpu_train.lock"))
SCORE_LOCK = LOCK.with_name(LOCK.stem + "_score.lock")
RETRY_PAUSE_S = 30
# Measured 2026-11-04: the trainer's allocator cache holds ~22.6 of 24 GB, so an overlapping
# score step fails (CUBLAS_STATUS_ALLOC_FAILED). Default: score steps also take the train lock.
SCORE_SHARED = os.environ.get("GPU_LOCK_SCORE_SHARED") == "1"


def is_train(args: tuple) -> bool:
    return str(args[0]) == "train"


def take(fh, mode: int, label: str) -> None:
    t0 = time.time()
    fcntl.flock(fh, mode)
    print(f"[gpulock] {label} waited {time.time() - t0:.0f}s", file=sys.stderr, flush=True)


def run_normal(inner, args: tuple) -> dict:
    step = grid_logged.step_name(args)
    if is_train(args) or not SCORE_SHARED:
        with LOCK.open("a") as fh:
            take(fh, fcntl.LOCK_EX, step)
            return inner(*args)
    with SCORE_LOCK.open("a") as fh:
        take(fh, fcntl.LOCK_SH, step)
        return inner(*args)


def run_exclusive(inner, args: tuple) -> dict:
    step = grid_logged.step_name(args)
    with LOCK.open("a") as fh, SCORE_LOCK.open("a") as sh:
        take(fh, fcntl.LOCK_EX, f"{step} retry(train lock)")
        take(sh, fcntl.LOCK_EX, f"{step} retry(score lock)")
        return inner(*args)


def locked_run_duel(inner):
    def run(*args) -> dict:
        try:
            return run_normal(inner, args)
        except Exception as e:
            print(f"[gpulock] {grid_logged.step_name(args)} failed ({e}); exclusive retry", file=sys.stderr, flush=True)
            time.sleep(RETRY_PAUSE_S)
            return run_exclusive(inner, args)
    return run


def main() -> None:
    logs = grid_logged.work_dir_from_argv(sys.argv) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    grid.run_duel = locked_run_duel(grid_fast_ledger.ledger_run_duel(logs, grid_logged.logged_run_duel(logs)))
    grid.main()


if __name__ == "__main__":
    main()
