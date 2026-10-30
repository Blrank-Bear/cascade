"""Paired per-seed differences vs base_nat across transfer.py reports (negative = better).

    python paired.py REPORT.json [REPORT.json ...]
"""
import json, sys, math
by = {}
for f in sys.argv[1:]:
    for k, v in json.load(open(f))["samples"].items():
        s = {}
        for seed, x in v["by_seed"].items():
            s[seed] = x if isinstance(x, (int, float)) else x.get("mean_score", x.get("score"))
            if isinstance(s[seed], dict) or s[seed] is None:
                s[seed] = sum(y["score"] for y in x.values()) / len(x)
        by.setdefault(k, s)
base = by["base_nat"]
print(f"{'arm':14s} {'mean d':>9s} {'sd':>8s} {'t':>6s}  per-seed d (negative = better than base)")
for k, s in sorted(by.items(), key=lambda kv: sum(kv[1].values())):
    d = [s[x] - base[x] for x in base if x in s]
    m = sum(d) / len(d); sd = math.sqrt(sum((y - m) ** 2 for y in d) / max(1, len(d) - 1))
    t = m / (sd / math.sqrt(len(d))) if sd else float("nan")
    print(f"{k:14s} {m:+9.5f} {sd:8.5f} {t:6.2f}  {[round(y, 4) for y in d]}")
