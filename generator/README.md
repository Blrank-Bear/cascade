# Working generator

Base: Lane A king `04e226724e3b` (unchanged copy in `reference/kings/2026-10-22-04e226724e3b/`).

- Outermost class `Generator` = v2 pack layer: yields `{"values": (32, 4096) float32, "groups": int64[32]}`.
- `_V2PackParent` = the king stream (pre-v2 rows), kept byte-identical to the baseline except for v2 budget constants.
- Being refactored into atomic functions (see CLAUDE.md).

Checks (WSL):
- `tests/golden/run.sh check` - byte-identical regression (inner king stream + v2 records)
- `tests/v2/validate.py generator` - cascade SeriesValidator under the v2 policy, determinism, duplicates, channel corr
- `tests/perf/run.sh` - throughput and memory under v2 child limits

See `notes/WEAKNESSES.md`. Not yet a submission.
