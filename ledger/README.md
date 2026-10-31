# Experiment ledger

Every performance measurement of our code is recorded here and analysed feature by feature.

- **`experiments.jsonl`** holds one record per measurement (append-only). Each record has:
  - git commit and generator sha256 (captured at training time from now on);
  - each arm's switch files and the budget (train seed, hours, config);
  - per-arm training steps and per-cell verdicts;
  - per-horizon and per-domain effects vs the reference;
  - validity checks: equal steps, same generator, no failures.
- **`analysis.md` / `analysis.json`** is the output of `tools/ledger/analyze.py`: per feature, results across seeds with mean / sd / t, per-horizon and per-domain effects, and a verdict from fixed rules. It also lists every excluded record and why.

## Workflow (one feature at a time)

1. Each test arm differs from the reference by exactly **one** switch file. Multi-change arms are excluded from the analysis.
2. Run each feature on **at least 3 training seeds**, with equal steps (`chain.v2-28m-mb2-steps.toml`), via `tools/duel/grid_fast_ledger.py`.
3. Snapshot the grid to the local machine (`tools/ledger/sync_grid.sh GRID`), ingest it (`tools/ledger/ingest_grid.py SNAPSHOT --grid GRID --seed S --hours H --config CFG`), then run `tools/ledger/analyze.py`.
4. Only an **ADOPT-CANDIDATE** feature is turned on. It becomes the new reference, and the next feature is tested on top of it.
5. A REJECT stays off. INCONCLUSIVE needs more seeds.

## Benchmark gate (v2, enforced on chain)
- `tools/ledger/compare_bench.py ARM.json REF.json` gives aggregate and per-task ratios and win rates per suite.
- `tools/ledger/bench_gate_check.py ARM.json REF.json` runs **upstream's own** `evaluate_bench_gate` (rule `avg_noninf_winrate`).
  - The real gate needs all four suites, FEV included. Without FEV it reports "not computable", so the script also runs the same rule on the suites present.
- **Adoption also requires passing the gate.** A feature that wins the private pool can still be blocked if its suite-equal task win rate falls below 0.5.

### Result: jsz05dr60 vs base (grid 4 checkpoints, seed 0, 396 steps; multi-feature arm, gate risk only)
- **Aggregate ratios are slightly better:** GIFT 0.999, BOOM 0.970, TIME 0.997. Worst ratio LCB 0.991.
- **Task win rate fails the gate:** GIFT 0.41, BOOM 0.55, TIME 0.38, so 0.448 < 0.5 on 3 suites.
- **FEV is not run yet,** so the real 4-suite gate is uncomputable.
- **4-suite gate (diagnostic):** FEV run on CPU (unpinned fev-bench list; 35/100 multivariate tasks are skipped by upstream's univariate adapter, so the report is "partial"). Treating the 65 scored tasks as the suite, upstream's gate **fails: win rate 0.459 < 0.5**.
  - Win rates: GIFT 0.41, BOOM 0.555, TIME 0.378, FEV 0.492.
  - avg ratio 0.991; worst LCB 0.990 (ratios fine).
  - Lesson: a pool gain is not enough. Features must win more tasks than they lose across GIFT/TIME/FEV, not just improve averages.
