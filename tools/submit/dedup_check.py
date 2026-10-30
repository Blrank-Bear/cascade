"""Dedup self-check: our package's fingerprints vs. the published king (static read only).

    python dedup_check.py PKG_DIR KING_DIR

Uses upstream's own fingerprinting (cascade.interface.dedup.fingerprint_dir). Any
identical tree/token/masked digest is an admission drop, so all must differ.
Module-sketch containment is informational: building on a published king is allowed.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

from cascade.interface.dedup import fingerprint_dir, module_sketches, sketch_containment

DIGEST_FIELDS = ("tree_sha256", "token_sha256", "masked_sha256", "py_token_sha256", "py_masked_sha256")


def digests(fp) -> dict:
    d = asdict(fp) if is_dataclass(fp) else dict(fp)
    return {k: v for k, v in d.items() if k in DIGEST_FIELDS or k.endswith("_sha256")}


def max_containment(ours: Path, king: Path) -> float:
    def sk(p: Path):
        return [frozenset(m["sketch"]) for m in module_sketches(p)]
    best = 0.0
    for a in sk(ours):
        for b in sk(king):
            best = max(best, sketch_containment(b, a))
    return best


def main() -> None:
    pkg, king = Path(sys.argv[1]), Path(sys.argv[2])
    ours_d, king_d = digests(fingerprint_dir(pkg)), digests(fingerprint_dir(king))
    same = sorted(k for k in ours_d if ours_d.get(k) and ours_d.get(k) == king_d.get(k))
    try:
        contain = round(max_containment(pkg, king), 4)
    except Exception as e:  # informational only
        contain = f"n/a ({type(e).__name__}: {e})"
    report = {"identical_digests": same, "pass": not same, "king_module_containment": contain,
              "compared": sorted(ours_d)}
    print(json.dumps(report, indent=1))
    sys.exit(0 if not same else 1)


if __name__ == "__main__":
    main()
