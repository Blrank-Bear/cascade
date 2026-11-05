"""Unit test for the ovf per-family overlay rates (k13 foundation).

Checks: empty map = ungated ovl (byte-identical); default 0 removes every overlay change;
a partial mute changes fewer rows and is deterministic; every looked-up record has a family;
the muted families do occur in the stream.

    python -I tests/k13/test_ovf.py GEN_DIR
"""
import collections
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "golden"))
import harness  # noqa: E402

N, TAKE, K0 = 2000, 60, 30
WORK = ROOT / ".claude-work" / "tmp" / "test_ovf"
MUTE = ["energy_load_price_solar", "grid_flow", "dispatch_price", "spiky_price", "clinical_bounded_vitals",
        "epi_renewal", "reported_epi_counts", "epi_decay", "physio_quasiperiodic"]


def run(gen_dir: Path, ovl: dict | None, tag: str, seed: int = 0):
    d = WORK / tag
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for f in ("generator.py", "config.json"):
        shutil.copyfile(gen_dir / f, d / f)
    if ovl is not None:
        (d / "v2_ovl.json").write_text(json.dumps(ovl))
    m = harness.load_module(d)
    m._LCP_K0 = K0
    fams = collections.Counter()
    inner = m._ovf_rate_mult
    def spy(cfg, fam):
        fams[fam] += 1
        return inner(cfg, fam)
    m._ovf_rate_mult = spy
    out = []
    it = m.Generator(str(d), seed=seed).generate(N)
    for y in it:
        out.append(np.array(y["values"]))
        if len(out) >= TAKE:
            break
    it.close()
    for k in [k for k in sys.modules if k == "generator"]:
        del sys.modules[k]
    sys.path.remove(str(d))
    return out, fams


def changed_rows(a: list, b: list) -> float:
    return float(np.mean([np.mean(np.any(x != y, axis=1)) for x, y in zip(a, b)]))


def main() -> None:
    gen = Path(sys.argv[1]).resolve()
    both = {"level_rate": 0.15, "amp_rate": 0.15}
    mute_cfg = {**both, "family_rate_mult": {f: 0.0 for f in MUTE}}
    base, _ = run(gen, None, "base")
    ovl, _ = run(gen, both, "ovl")
    empty, _ = run(gen, {**both, "family_rate_mult": {}}, "empty")
    allzero, _ = run(gen, {**both, "family_rate_default": 0.0}, "allzero")
    mute, fams = run(gen, mute_cfg, "mute")
    again, _ = run(gen, mute_cfg, "again")
    assert all(np.array_equal(x, y) for x, y in zip(ovl, empty)), "empty map not identical to ovl"
    assert all(np.array_equal(x, y) for x, y in zip(mute, again)), "not deterministic"
    c_ovl, c_mute, c_zero = changed_rows(base, ovl), changed_rows(base, mute), changed_rows(base, allzero)
    muted = sum(fams[f] for f in MUTE)
    print(json.dumps({"changed_ovl": round(c_ovl, 3), "changed_mute": round(c_mute, 3), "changed_allzero": c_zero,
                      "records": sum(fams.values()), "no_family": fams[None], "muted_records": muted,
                      "top_families": fams.most_common(6)}))
    assert c_zero == 0.0, "default 0 should remove every overlay"
    assert fams[None] == 0, "record without a family"
    assert muted > 0 and c_mute < c_ovl
    print("OK")


if __name__ == "__main__":
    main()
