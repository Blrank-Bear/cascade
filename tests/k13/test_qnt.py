"""Unit test for the qnt quantization layer (k13 foundation): off = byte-identical, rate changes rows,
quantized channels sit on one tick grid, integer / constant channels untouched, determinism, finiteness.

    python -I tests/k13/test_qnt.py GEN_DIR
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
WORK = ROOT / ".claude-work" / "tmp" / "test_qnt"


def run(gen_dir: Path, files: dict, tag: str, seed: int = 0):
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
        if len(out) >= TAKE:
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
    walk = np.cumsum(rng.normal(size=4096))
    cfg = {"rel_res_min": 1.0, "rel_res_max": 1.0}
    q = m._qnt_channel(walk, np.random.default_rng(1), cfg)
    tick = m._qnt_nice_tick(m._qnt_typical_step(walk))
    assert np.allclose(q / tick, np.round(q / tick)), "not on the tick grid"
    ints = np.round(walk)
    assert np.array_equal(m._qnt_channel(ints, np.random.default_rng(1), cfg), ints), "integer channel changed"
    const = np.full(4096, 3.7)
    assert np.array_equal(m._qnt_channel(const, np.random.default_rng(1), cfg), const), "constant channel changed"


def main() -> None:
    gen = Path(sys.argv[1]).resolve()
    base, m = run(gen, {}, "base")
    off, _ = run(gen, {"v2_qnt.json": {"rate": 0.0}}, "off")
    on, _ = run(gen, {"v2_qnt.json": {"rate": 0.5}}, "on")
    again, _ = run(gen, {"v2_qnt.json": {"rate": 0.5}}, "again")
    stack = {"v2_qnt.json": {"rate": 0.5}, "v2_ovl.json": {"level_rate": 0.15, "amp_rate": 0.15, "phase": "trunk"}}
    both, _ = run(gen, stack, "stack")
    check_channel(m)
    assert all(np.array_equal(x, y) for x, y in zip(base, off)), "rate 0 not identical"
    assert all(np.array_equal(x, y) for x, y in zip(on, again)), "not deterministic"
    assert all(np.isfinite(x).all() and np.abs(x).max() <= 3.4e38 for x in on + both)
    c_on, c_both = changed_rows(base, on), changed_rows(base, both)
    print(json.dumps({"changed_qnt05": round(c_on, 3), "changed_qnt05_ovltrunk": round(c_both, 3)}))
    assert 0.05 < c_on < 0.9
    print("OK")


if __name__ == "__main__":
    main()
