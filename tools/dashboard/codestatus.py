"""Code-update status: our repo, the generator's v2 stage switches, upstream changes,
and whether the GPU server's copy matches local files.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

STAGE_FILES = ("v2_mix.json", "v2_groups.json", "v2_history.json", "v2_pool.json", "v2_pool2.json",
               "v2_flat.json", "v2_quant.json", "v2_jumps.json")
SYNC_FILES = ("generator/generator.py", "generator/config.json", "tools/duel/duel.py", "tools/duel/grid.py",
              "tools/duel/grid_logged.py", "tools/duel/make_v2_cfg.py", "tools/dashboard/collect.py",
              "tools/dashboard/serve.py")
UPSTREAM_BRANCH = "cascade-v2"
COMMITS_SHOWN = 15


def git(repo: Path, *args: str, timeout: float = 60) -> str:
    # --no-optional-locks: a dashboard poll must never take index.lock from real commits
    cmd = ["git", "--no-optional-locks", "-c", f"safe.directory={repo}", "-C", str(repo), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


def commit_rows(repo: Path, rev: str = "HEAD", n: int = COMMITS_SHOWN) -> list[dict]:
    out = git(repo, "log", rev, f"-{n}", "--format=%h%x1f%ct%x1f%an%x1f%s", "--shortstat")
    rows: list[dict] = []
    for line in out.splitlines():
        if "\x1f" in line:
            h, t, a, s = line.split("\x1f", 3)
            rows.append({"hash": h, "t": int(t), "author": a, "subject": s, "files": None})
        elif rows and "changed" in line:
            m = re.search(r"(\d+) files? changed", line)
            rows[-1]["files"] = int(m.group(1)) if m else None
    return rows


def dirty_files(repo: Path) -> list[str]:
    return [l[3:] for l in git(repo, "status", "--porcelain").splitlines() if l.strip()]


def repo_section(repo: Path) -> dict:
    return {"branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
            "head": git(repo, "rev-parse", "--short", "HEAD").strip(),
            "dirty": dirty_files(repo), "commits": commit_rows(repo),
            "n_commits": int(git(repo, "rev-list", "--count", "HEAD").strip() or 0)}


def file_digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def stage_switches(gen_dir: Path) -> list[dict]:
    rows = []
    for name in STAGE_FILES:
        p = gen_dir / name
        body = json.loads(p.read_text()) if p.is_file() else None
        rows.append({"file": name, "present": body is not None, "config": body})
    return rows


def generator_section(gen_dir: Path) -> dict:
    src = gen_dir / "generator.py"
    return {"sha256": file_digest(src), "lines": src.read_text(errors="replace").count("\n"),
            "bytes": src.stat().st_size, "mtime": src.stat().st_mtime, "switches": stage_switches(gen_dir)}


def upstream_fetch(repo: Path) -> None:
    git(repo, "fetch", "-q", "origin", UPSTREAM_BRANCH, timeout=120)


def upstream_section(repo: Path) -> dict:
    remote = f"origin/{UPSTREAM_BRANCH}"
    behind = commit_rows(repo, f"HEAD..{remote}", n=30)
    return {"head": git(repo, "rev-parse", "--short", "HEAD").strip(),
            "remote_head": git(repo, "rev-parse", "--short", remote).strip(),
            "behind": behind, "recent": commit_rows(repo, remote, n=8),
            "fetched_head_t": (repo / ".git" / "FETCH_HEAD").stat().st_mtime if (repo / ".git" / "FETCH_HEAD").exists() else None}


def server_digests(ssh_cmd: list[str], remote_root: str) -> dict[str, str]:
    script = f"cd {remote_root} && sha256sum {' '.join(SYNC_FILES)} 2>/dev/null; git -C upstream rev-parse --short HEAD 2>/dev/null | sed 's/^/UPSTREAM /'"
    out = subprocess.run([*ssh_cmd, script], capture_output=True, text=True, timeout=30).stdout
    digests = {}
    for line in out.splitlines():
        if line.startswith("UPSTREAM "):
            digests["__upstream__"] = line.split()[1]
        elif "  " in line:
            h, f = line.split("  ", 1)
            digests[f.strip()] = h
    return digests


def sync_section(root: Path, remote: dict[str, str], upstream_head: str) -> dict:
    files = [{"file": f, "local": (file_digest(root / f) or "")[:12], "server": (remote.get(f) or "")[:12]} for f in SYNC_FILES]
    for r in files:
        r["state"] = "missing" if not r["server"] else "same" if r["local"] == r["server"] else "differs"
    return {"files": files, "n_differ": sum(r["state"] != "same" for r in files),
            "server_upstream": remote.get("__upstream__"), "local_upstream": upstream_head,
            "reachable": bool(remote)}
