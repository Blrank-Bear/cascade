"""Throughput check: steady yields/s of a package at the production per-child n (5e10 points / 32 children /
min_length 64 + 2), one process. A child must reach >= 2.21 yields/s (11,921 yields in the 5400 s window).

    python -I yield_rate.py GEN_DIR TAKE
"""
import importlib.util, sys, time
from pathlib import Path
import numpy as np
d, take = Path(sys.argv[1]).resolve(), int(sys.argv[2])
sys.path.insert(0, str(d))
spec = importlib.util.spec_from_file_location("generator", d / "generator.py")
m = importlib.util.module_from_spec(spec); sys.modules["generator"] = m; spec.loader.exec_module(m)
N = 50_000_000_000 // 32 // 64 + 2
it = m.Generator(str(d), seed=12345).generate(N)
t0 = time.time(); first = None
for i, y in enumerate(it):
    v = np.asarray(y["values"])
    assert v.shape == (32, 4096) and np.isfinite(v).all()
    if i == 9:
        first = time.time()
    if i + 1 >= take:
        break
t1 = time.time()
print(f"{d.name}: {take} yields, startup+10 {first - t0:.1f}s, steady {(take - 10) / (t1 - first):.2f} yields/s (need >= 2.21)")
