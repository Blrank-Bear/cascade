"""Per-source mean log-MASE delta (arm - base) on the worst-error sources (ledger/error_sources_*.json), across seeds 0-2.

    python source_deltas.py ARM [ARM ...]   (cwd = repo root)
"""
import json, math, glob, sys
from collections import defaultdict
top = [r["source"] for r in json.load(open("ledger/error_sources_base_s012.json"))["top"]]
arms = sys.argv[1:]
d = {a: defaultdict(list) for a in arms}
for g in ("grid_gpu4", "grid_gpu4s1", "grid_gpu4s2"):
    snap = sorted(glob.glob(f".claude-work/grids/{g}/*/"))[-1]
    for a in arms:
        for f in glob.glob(f"{snap}{g}/scores/{a}__*.json"):
            bf = f.replace(f"/{a}__", "/base__")
            A, B = json.load(open(f))["scores"], json.load(open(bf))["scores"]
            for ra, rb in zip(A, B):
                if ra.get("source") in top and ra.get("mase") and rb.get("mase"):
                    d[a][ra["source"]].append(math.log(max(ra["mase"], 1e-9)) - math.log(max(rb["mase"], 1e-9)))
print(f"{'source':44s} " + " ".join(f"{a:>10s}" for a in arms))
tot = defaultdict(list)
for s in top:
    vals = []
    for a in arms:
        x = d[a].get(s, [])
        tot[a] += x
        vals.append(f"{sum(x)/len(x):+10.3f}" if x else f"{'-':>10s}")
    print(f"{s[:44]:44s} " + " ".join(vals))
print(f"{'ALL top sources (mean)':44s} " + " ".join(f"{sum(tot[a])/len(tot[a]):+10.3f}" for a in arms))
