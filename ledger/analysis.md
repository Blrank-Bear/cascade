# Experiment ledger analysis (feature by feature)

Rules: ADOPT-CANDIDATE needs ≥3 seeds, every seed > 0, t ≥ 2.5, no horizon below −0.5%. Only valid records and single-feature arms are used.

| Feature (switch vs reference) | Arm | Seeds | Per-seed gain | Mean | sd | t | Horizons (64/256/720) | Verdict |
|---|---|---|---|---|---|---|---|---|
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 5.0, "size_min": 0.5}}` | j100sz05 | [0, 1, 2] | -0.28%, +1.00%, +0.23% | +0.32% | +0.64% | 0.86 | +1.21% / +0.20% / -0.46% | **INCONCLUSIVE** |
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 2.5, "size_min": 0.25}}` | jsz025 | [0, 1, 2] | +0.20%, +0.63%, -0.24% | +0.19% | +0.44% | 0.77 | +1.30% / -0.13% / -0.59% | **INCONCLUSIVE** |
| `{"v2_quant.json": {"rate": 0.5}}` | q50 | [0, 1, 2] | +0.14%, +0.13%, -0.08% | +0.06% | +0.12% | 0.86 | +0.11% / +0.10% / -0.03% | **INCONCLUSIVE** |
| `{"v2_pool2.json": {"rate": 0.25}}` | p2_25 | [0, 1, 2] | -0.50%, +0.61%, -0.36% | -0.08% | +0.60% | -0.23 | +0.11% / +0.17% / -0.53% | **INCONCLUSIVE** |
| `{"v2_dock.json": {"replace_rate": 0.6}}` | dr60only | [0, 1, 2] | -0.15%, +0.29%, -0.40% | -0.09% | +0.35% | -0.44 | -0.02% / +0.02% / -0.27% | **INCONCLUSIVE** |
| `{"v2_mix.json": {"rate": 0.3}}` | mix30 | [0, 1, 2] | -0.81%, -0.06%, -1.48% | -0.79% | +0.71% | -1.92 | -0.51% / -0.96% / -0.89% | **REJECT** |
| `{"v2_history.json": {"rate": 0.55}}` | h55 | [0, 1, 2] | -2.90%, -1.11%, -3.03% | -2.35% | +1.07% | -3.79 | -3.54% / -2.04% / -1.48% | **REJECT** |

## Per-domain effect (mean log MASE arm/reference across seeds; negative = better)

- **j100sz05**: transport -0.024, econ_fin -0.017, nature -0.005, sales -0.003, energy +0.006, web_cloudops +0.006, healthcare +0.011
- **jsz025**: transport -0.023, econ_fin -0.012, sales -0.007, nature -0.005, energy +0.009, web_cloudops +0.009, healthcare +0.013
- **q50**: web_cloudops -0.005, healthcare -0.005, sales -0.003, energy +0.001, econ_fin +0.002, nature +0.002, transport +0.004
- **p2_25**: healthcare -0.004, web_cloudops -0.004, nature -0.001, sales +0.002, energy +0.002, econ_fin +0.003, transport +0.006
- **dr60only**: econ_fin -0.003, healthcare -0.003, web_cloudops -0.003, energy -0.001, transport -0.001, nature +0.003, sales +0.006
- **mix30**: energy -0.002, web_cloudops -0.002, nature -0.001, healthcare +0.003, sales +0.009, transport +0.011, econ_fin +0.012
- **h55**: healthcare +0.003, energy +0.012, web_cloudops +0.018, econ_fin +0.022, nature +0.032, sales +0.037, transport +0.041

## Excluded

- `grid_gpu2@20261031T021943Z`: invalid: equal_steps
- `grid_gpu2s1@20261031T021943Z`: invalid: equal_steps
- `grid_gpu4@20261031T021943Z:jcombo`: multi-feature (3 switches differ)
- `grid_gpu4@20261031T021943Z:jsz05dr60`: multi-feature (2 switches differ)
- `grid_gpu4@20261031T021943Z:jsz05sing`: multi-feature (2 switches differ)
- `grid_gpu4s1@20261031T025733Z:j30sz05dr60`: multi-feature (2 switches differ)
- `grid_gpu4s1@20261031T025733Z:jsz025dr60`: multi-feature (2 switches differ)
- `grid_gpu4s1@20261031T025733Z:jsz05dr60`: multi-feature (2 switches differ)
