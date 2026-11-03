"""Per-seed (horizon x domain) gain of the 8-seed arms, to see if seed 0's base is lucky in some cells."""
import json, sys
from pathlib import Path
sys.path.insert(0, "tools/duel")
import probe_cells as P
snaps = {}
for l in open("ledger/experiments.jsonl"):
    d = json.loads(l)
    if d.get("valid"):
        for a in d["judged_arms"]:
            snaps[(d["budget"]["train_seed"], a)] = Path(d["snapshot"]) / d["grid"]
arms = ["j100sz05", "jsz025", "q50"]
cells = [("720", "energy"), ("720", "web_cloudops"), ("720", "nature"), ("720", "*"), ("64", "*"), ("256", "*"), ("*", "*")]
print("seed " + " ".join("%14s" % ("%s|%s" % c) for c in cells))
rows = []
for s in range(8):
    acc = {c: [] for c in cells}
    for a in arms:
        if (s, a) not in snaps:
            continue
        cg = P.cell_gains(snaps[(s, a)], a, "base")
        for c in cells:
            if c in cg:
                acc[c].append(cg[c][0])
    m = {c: sum(v) / len(v) for c, v in acc.items() if v}
    rows.append(m)
    print("%4d " % s + " ".join("%+14.2f" % (100 * m.get(c, float("nan"))) for c in cells))
