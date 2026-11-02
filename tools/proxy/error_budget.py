"""Where could a 1% round-metric gain come from? Sum of excess log error by horizon x domain, base arm, seeds 0-2."""
import json, math, sys, glob
from collections import defaultdict
FLOOR_M, FLOOR_W = 1e-9, 1e-12
def wql(r):
    q, a = r.get("qloss_per_q") or [], r.get("abs_target") or 0.0
    return 2.0 * sum(q) / (len(q) * a) if q and a > 0 else None
files = sys.argv[1:]
cell = defaultdict(lambda: [0, 0.0, 0.0, 0])  # n, sum log err, excess over 0 (windows worse than seasonal naive), n bad
tot_n = 0
for f in files:
    for r in json.load(open(f))["scores"]:
        m, w = r.get("mase"), wql(r)
        if m is None or w is None: continue
        e = 0.5 * (math.log(max(m, FLOOR_M)) + math.log(max(w, FLOOR_W)))
        c = cell[(str(r.get("horizon")), r.get("domain", "?"))]
        c[0] += 1; c[1] += e; c[2] += max(0.0, math.log(max(m, FLOOR_M))); c[3] += m > 1
        tot_n += 1
need = 0.01 * tot_n
print(f"windows {tot_n}; a 1% metric gain = lowering mean half-log-error by 0.01 = {need:.0f} units in total\n")
print(f"{'h':>4s} {'domain':12s} {'n':>6s} {'mean err':>9s} {'MASE>1':>7s} {'excess logMASE':>15s} {'1% of cell':>10s}")
for (h, d), c in sorted(cell.items(), key=lambda kv: -kv[1][2]):
    print(f"{h:>4s} {d[:12]:12s} {c[0]:6d} {c[1]/c[0]:9.3f} {c[3]/c[0]:7.2f} {c[2]:15.0f} {0.01*c[0]:10.0f}")
