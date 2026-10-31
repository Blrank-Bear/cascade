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
