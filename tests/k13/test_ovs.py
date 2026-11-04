"""Unit test for the ovs seasonal gate on the ovl overlays (k13 foundation).

Checks: strength separates a sine from noise; gate 0 = ungated ovl (byte-identical stream);
gate on changes fewer rows than ungated, keeps finiteness and determinism.

    python -I tests/k13/test_ovs.py GEN_DIR
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
WORK = ROOT / ".claude-work" / "tmp" / "test_ovs"


def run(gen_dir: Path, ovl: dict | None, tag: str, seed: int = 0) -> list:
    d = WORK / tag
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for f in ("generator.py", "config.json"):
        shutil.copyfile(gen_dir / f, d / f)
    if ovl is not None:
        (d / "v2_ovl.json").write_text(json.dumps(ovl))
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


def check_strength(m) -> dict:
    t = np.arange(4096)
    rng = np.random.default_rng(0)
    sine = np.sin(2 * np.pi * t / 24.0) + 0.1 * rng.normal(size=t.size)
    noise = rng.normal(size=t.size)
    s_sine, s_noise = m._ovs_season_strength(sine, 4, 0.25), m._ovs_season_strength(noise, 4, 0.25)
    assert s_sine > 0.8 and s_noise < 0.05, (s_sine, s_noise)
    return {"sine": round(s_sine, 3), "noise": round(s_noise, 4)}


def main() -> None:
    gen = Path(sys.argv[1]).resolve()
    both = {"level_rate": 0.15, "amp_rate": 0.15}
    base, m = run(gen, None, "base")
    ovl, _ = run(gen, both, "ovl")
    gate0, _ = run(gen, {**both, "season_gate_max": 0.0}, "gate0")
    gated, _ = run(gen, {**both, "season_gate_max": 0.2}, "gated")
    again, _ = run(gen, {**both, "season_gate_max": 0.2}, "again")
    strength = check_strength(m)
    assert all(np.array_equal(x, y) for x, y in zip(ovl, gate0)), "gate 0 not identical to ovl"
    assert all(np.array_equal(x, y) for x, y in zip(gated, again)), "not deterministic"
    assert all(np.isfinite(x).all() and np.abs(x).max() <= 3.4e38 for x in gated)
    c_ovl, c_gated = changed_rows(base, ovl), changed_rows(base, gated)
    print(json.dumps({"strength": strength, "changed_ovl": round(c_ovl, 3), "changed_gated": round(c_gated, 3)}))
    assert 0.0 < c_gated < c_ovl, "gate did not reduce the overlay share"
    print("OK")


if __name__ == "__main__":
    main()
