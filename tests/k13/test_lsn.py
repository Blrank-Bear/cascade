"""Unit test for the lsn drifting-seasonal replacement layer (k13 foundation): off = byte-identical, rate changes
rows, deterministic, finite; replacement series are finite and non-constant, record shape kept; phase "cooldown"
leaves the trunk untouched.

    python -I tests/k13/test_lsn.py GEN_DIR
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
WORK = ROOT / ".claude-work" / "tmp" / "test_lsn"
OVL = {"v2_ovl.json": {"level_rate": 0.15, "amp_rate": 0.15, "phase": "trunk"}}


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
    cfg = dict(m._LSN_DEFAULTS)
    for k in range(20):
        y = m._lsn_series(np.random.default_rng(k), 4096, cfg)
        assert y.shape == (4096,) and np.isfinite(y).all() and float(np.ptp(y)) > 0.0
    a = np.random.default_rng(0).normal(size=(3, 4096))
    out = m._lsn_apply(a, 0, 0, {**cfg, "rate": 1.0})
    assert out.shape == a.shape and not np.array_equal(out, a)
    assert m._lsn_apply(a, 0, 0, {**cfg, "rate": 0.0}) is a


def main() -> None:
    gen = Path(sys.argv[1]).resolve()
    base, m = run(gen, OVL, "base")
    off, _ = run(gen, {**OVL, "v2_lsn.json": {"rate": 0.0}}, "off")
    on, _ = run(gen, {**OVL, "v2_lsn.json": {"rate": 0.3}}, "on")
    again, _ = run(gen, {**OVL, "v2_lsn.json": {"rate": 0.3}}, "again")
    cool, _ = run(gen, {**OVL, "v2_lsn.json": {"rate": 0.3, "phase": "cooldown"}}, "cool", take=20)
    check_channel(m)
    assert all(np.array_equal(x, y) for x, y in zip(base, off)), "rate 0 not identical"
    assert all(np.array_equal(x, y) for x, y in zip(on, again)), "not deterministic"
    assert all(np.array_equal(x, y) for x, y in zip(base[:20], cool)), "cooldown phase changed the trunk"
    assert all(np.isfinite(x).all() and np.abs(x).max() <= 3.4e38 for x in on)
    c_on = changed_rows(base, on)
    print(json.dumps({"changed_lsn30_over_ovl": round(c_on, 3)}))
    assert 0.1 < c_on < 0.9
    print("OK")


if __name__ == "__main__":
    main()
