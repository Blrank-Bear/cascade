# Experiment ledger analysis (feature by feature)

Rules: ADOPT-CANDIDATE needs ≥3 seeds, every seed > 0, t ≥ 2.5, no horizon below −0.5%. Only valid records and single-feature arms are used.

| Feature (switch vs reference) | Arm | Seeds | Per-seed gain | Mean | sd | t | Horizons (64/256/720) | Verdict |
|---|---|---|---|---|---|---|---|---|
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 2.5, "size_min": 0.25}}` | jsz025 | [0] | +0.20% | +0.20% | — | — | +1.34% / -0.29% / -0.46% | **INCONCLUSIVE** |
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 5.0, "size_min": 0.5}}` | j100sz05 | [0] | -0.28% | -0.28% | — | — | +0.63% / -0.51% / -0.96% | **INCONCLUSIVE** |

## Per-domain effect (mean log MASE arm/reference across seeds; negative = better)

- **jsz025**: transport -0.024, econ_fin -0.010, sales -0.008, nature -0.003, web_cloudops +0.005, healthcare +0.006, energy +0.013
- **j100sz05**: transport -0.021, econ_fin -0.006, web_cloudops +0.005, nature +0.007, sales +0.008, energy +0.012, healthcare +0.013

## Excluded

- `grid_gpu2@20261031T021943Z`: invalid: equal_steps
- `grid_gpu2s1@20261031T021943Z`: invalid: equal_steps
- `grid_gpu4@20261031T021943Z:jcombo`: multi-feature (3 switches differ)
- `grid_gpu4@20261031T021943Z:jsz05dr60`: multi-feature (2 switches differ)
- `grid_gpu4@20261031T021943Z:jsz05sing`: multi-feature (2 switches differ)
