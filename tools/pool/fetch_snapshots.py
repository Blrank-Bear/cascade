"""Fetch the newest retired cascade eval-pool snapshots from Hugging Face.

The active pool is private; retired snapshots are mirrored byte-exact on HF about
48 h after they are superseded. They are the closest legal proxy for the live test
set, and each unpacked folder is directly usable as `cascade iterate --pool-dir`.

    python fetch_snapshots.py --out DIR [--latest 3] [--stats]

Each snapshot lands in DIR/<as_of>-block-<N>/ (sha256-verified, *.npy + metadata.json).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

REPO = "Tensor-Link/cascade-eval-pool"
API_TREE = f"https://huggingface.co/api/datasets/{REPO}/tree/main/snapshots"
RESOLVE = f"https://huggingface.co/datasets/{REPO}/resolve/main/snapshots"
ALLOWED_SUFFIXES = (".npy", ".json")


def http_get(url: str, timeout: int = 600) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def list_block_snapshots() -> list[str]:
    entries = json.loads(http_get(API_TREE, timeout=60))
    names = [e["path"].split("/")[-1] for e in entries if e.get("type") == "directory"]
    return sorted((n for n in names if "-block-" in n), key=snapshot_block)


def snapshot_block(name: str) -> int:
    return int(name.rsplit("-block-", 1)[1])


def expected_sha256(name: str) -> str:
    return http_get(f"{RESOLVE}/{name}/POOL_SHA256", timeout=60).decode().split()[0].strip()


def download_tar(name: str) -> bytes:
    return http_get(f"{RESOLVE}/{name}/block-{snapshot_block(name)}.tar")


def verify_sha256(data: bytes, expected: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"sha256 mismatch: {actual} != {expected}")


def safe_member(member: tarfile.TarInfo) -> bool:
    name = member.name
    return (member.isfile() and not name.startswith("/") and ".." not in Path(name).parts
            and name.endswith(ALLOWED_SUFFIXES))


def extract_flat(data: bytes, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if not safe_member(member):
                continue
            payload = tar.extractfile(member).read()
            (dest / Path(member.name).name).write_bytes(payload)
            count += 1
    return count


def fetch_snapshot(name: str, out: Path) -> Path:
    dest = out / name
    marker = dest / ".verified"
    if marker.is_file():
        return dest
    data = download_tar(name)
    verify_sha256(data, expected_sha256(name))
    extract_flat(data, dest)
    marker.write_text(hashlib.sha256(data).hexdigest() + "\n")
    return dest


def pool_stats(dest: Path) -> dict:
    import numpy as np
    meta = json.loads((dest / "metadata.json").read_text()) if (dest / "metadata.json").is_file() else {}
    lengths = [int(np.load(p, mmap_mode="r").shape[-1]) for p in sorted(dest.glob("*.npy"))]
    channels = [int(np.atleast_2d(np.load(p, mmap_mode="r")).shape[0]) for p in sorted(dest.glob("*.npy"))]
    return {
        "series": len(lengths),
        "multichannel_series": sum(c > 1 for c in channels),
        "length_quantiles": [int(q) for q in np.quantile(lengths, [0.05, 0.25, 0.5, 0.75, 0.95])] if lengths else [],
        "by_domain": count_field(meta, "domain"),
        "by_freq": count_field(meta, "freq"),
        "sources": len({m.get("source") for m in meta.values()}),
    }


def count_field(meta: dict, field: str) -> dict:
    counts: dict[str, int] = {}
    for m in meta.values():
        key = str(m.get(field))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--latest", type=int, default=3)
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    names = list_block_snapshots()[-args.latest:]
    report = {}
    for name in names:
        dest = fetch_snapshot(name, args.out)
        report[name] = pool_stats(dest) if args.stats else str(dest)
        print(name, "ok", flush=True)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
