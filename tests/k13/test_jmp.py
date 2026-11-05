"""Unit test for the jmp shifts / outliers layer (k13 foundation): off = byte-identical, rate changes rows,
deterministic, finite; grid channels stay on their grid; binary / constant channels untouched;
non-negative channels stay non-negative; phase "cooldown" leaves the trunk untouched.

    python -I tests/k13/test_jmp.py GEN_DIR
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "golden"))
import harness  # noqa: E402

N, TAKE, K0 = 2000, 60, 30
WORK = ROOT / ".claude-work" / "tmp" / "test_jmp"
C1 = {"v2_ovl.json": {"level_rate": 0.15, "amp_rate": 0.15, "phase": "trunk"},
      "v2_qnt.json": {"rate": 0.5}}


def run(gen_dir: Path, files: dict, tag: str, seed: int = 0, take: int = TAKE):
    d = WORK / tag
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for f in ("generator.py", "config.json"):
        shutil.copyfile(gen_dir / f, d / f)
    for name, body in files.items():
        (d / name).write_text(json.dumps(body))
    m = harness.load_module(d)
    m._LCP_K0 = K0
    out = []
    it = m.Generator(str(d), seed=seed).generate(N)
    for y in it:
        out.append(np.array(y["values"]))
        if len(out) >= take:
            break
    it.close()
    for k in [k for k in sys.modules if k == "generator"]:
        del sys.modules[k]
    sys.path.remove(str(d))
    return out, m


def changed_rows(a: list, b: list) -> float:
    return float(np.mean([np.mean(np.any(x != y, axis=1)) for x, y in zip(a, b)]))


def check_channel(m) -> None:
    rng = np.random.default_rng(0)
    cfg = {**m._JMP_DEFAULTS, "max_shifts": 24.0, "max_outliers": 20.0}
    ints = np.abs(np.round(np.cumsum(rng.normal(size=4096) * 3)))
    y = m._jmp_channel(ints, np.random.default_rng(1), cfg)
    assert not np.array_equal(y, ints) and np.array_equal(y, np.round(y)), "integer channel left its grid"
    assert y.min() >= 0.0, "non-negative channel went negative"
    tick = np.round(np.cumsum(rng.normal(size=4096)) / 0.05) * 0.05
    y = m._jmp_channel(tick, np.random.default_rng(1), cfg)
    assert np.allclose(y / 0.05, np.round(y / 0.05), atol=1e-6), "tick channel left its grid"
    walk = np.cumsum(rng.normal(size=4096))
    assert not np.array_equal(m._jmp_channel(walk, np.random.default_rng(1), cfg), walk)
    binary = (rng.random(4096) < 0.3).astype(np.float64)
    const = np.full(4096, 3.7)
    for ch in (binary, const):
        assert np.array_equal(m._jmp_channel(ch, np.random.default_rng(1), cfg), ch), "binary/constant changed"


def main() -> None:
    gen = Path(sys.argv[1]).resolve()
    base, m = run(gen, C1, "base")
    off, _ = run(gen, {**C1, "v2_jmp.json": {"rate": 0.0}}, "off")
    on, _ = run(gen, {**C1, "v2_jmp.json": {"rate": 1.0}}, "on")
    again, _ = run(gen, {**C1, "v2_jmp.json": {"rate": 1.0}}, "again")
    cool, _ = run(gen, {**C1, "v2_jmp.json": {"rate": 1.0, "phase": "cooldown"}}, "cool", take=20)
    check_channel(m)
    assert all(np.array_equal(x, y) for x, y in zip(base, off)), "rate 0 not identical"
    assert all(np.array_equal(x, y) for x, y in zip(on, again)), "not deterministic"
    assert all(np.array_equal(x, y) for x, y in zip(base[:20], cool)), "cooldown phase changed the trunk"
    assert all(np.isfinite(x).all() and np.abs(x).max() <= 3.4e38 for x in on)
    c_on = changed_rows(base, on)
    print(json.dumps({"changed_jmp100_over_c1": round(c_on, 3)}))
    assert 0.2 < c_on < 1.0
    print("OK")


if __name__ == "__main__":
    main()
