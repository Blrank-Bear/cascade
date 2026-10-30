"""Build a submission folder from generator/ plus a named switch profile.

    python build_package.py PROFILE [--out submission]

PROFILE is tools/submit/profiles/<PROFILE>.json: {"switches": {"v2_jumps.json": {...}, ...},
"note": "..."}. The folder gets exactly the files a submission needs (generator.py,
config.json, requirements.txt) plus the profile's switch files, and a MANIFEST.json
outside it (sha256 per file, git HEAD) so the shipped bytes are auditable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES = Path(__file__).resolve().parent / "profiles"
GEN_FILES = ("generator.py", "config.json", "requirements.txt")


def load_profile(name: str) -> dict:
    return json.loads((PROFILES / f"{name}.json").read_text())


def fresh_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def copy_generator(dst: Path) -> None:
    for f in GEN_FILES:
        shutil.copyfile(ROOT / "generator" / f, dst / f)


def write_switches(dst: Path, switches: dict) -> None:
    for fname, body in switches.items():
        (dst / fname).write_text(json.dumps(body) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()


def git_dirty_generator() -> bool:
    out = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "generator"], capture_output=True, text=True)
    return bool(out.stdout.strip())


def manifest(pkg: Path, profile_name: str, profile: dict) -> dict:
    return {"profile": profile_name, "note": profile.get("note"), "git_head": git_head(),
            "generator_dirty": git_dirty_generator(),
            "files": {p.name: sha256(p) for p in sorted(pkg.iterdir()) if p.is_file()}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--out", type=Path, default=ROOT / "submission")
    args = ap.parse_args()
    profile = load_profile(args.profile)
    pkg = fresh_dir(args.out / args.profile / "generator")
    copy_generator(pkg)
    write_switches(pkg, profile.get("switches", {}))
    m = manifest(pkg, args.profile, profile)
    (args.out / args.profile / "MANIFEST.json").write_text(json.dumps(m, indent=1) + "\n")
    print(json.dumps(m, indent=1))


if __name__ == "__main__":
    main()
