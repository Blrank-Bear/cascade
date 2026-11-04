"""Unit test for the ovl layer on the k13 foundation: rates, phases, finiteness, determinism.

    python -I tests/k13/test_ovl.py GEN_DIR
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "golden"))
import harness  # noqa: E402

N, TAKE, K0 = 2000, 60, 30


def run(gen_dir: Path, ovl: dict | None, seed: int = 0) -> list:
    d = Path(tempfile.mkdtemp())
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
    return out


def changed_rows(a: list, b: list) -> np.ndarray:
    return np.array([float(np.mean(np.any(x != y, axis=1))) for x, y in zip(a, b)])


def main() -> None:
    gen = Path(sys.argv[1]).resolve()
    base = run(gen, None)
    both = {"level_rate": 0.15, "amp_rate": 0.15}
    allp = run(gen, both)
    again = run(gen, both)
    trunk = run(gen, {**both, "phase": "trunk"})
    cool = run(gen, {**both, "phase": "cooldown"})
    assert all(np.array_equal(x, y) for x, y in zip(allp, again)), "not deterministic"
    assert all(np.isfinite(x).all() and np.abs(x).max() <= 3.4e38 for x in allp + trunk + cool)
    c_all, c_tr, c_co = changed_rows(base, allp), changed_rows(base, trunk), changed_rows(base, cool)
    print(json.dumps({"changed_row_share_all": round(float(c_all.mean()), 3),
                      "trunk_before_K0": round(float(c_tr[:K0 - 2].mean()), 3),
                      "trunk_after_K0": round(float(c_tr[K0 + 2:].mean()), 3),
                      "cool_before_K0": round(float(c_co[:K0 - 2].mean()), 3),
                      "cool_after_K0": round(float(c_co[K0 + 2:].mean()), 3)}))
    assert c_all.mean() > 0.1
    assert c_tr[K0 + 2:].mean() < 0.02 and c_co[:K0 - 2].mean() < 0.02, "phase gating broken"
    print("OK")


if __name__ == "__main__":
    main()
