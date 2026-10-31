# Experiment ledger analysis (feature by feature)

Rules: ADOPT-CANDIDATE needs ≥3 seeds, every seed > 0, t ≥ 2.5, no horizon below −0.5%. Only valid records and single-feature arms are used.

| Feature (switch vs reference) | Arm | Seeds | Per-seed gain | Mean | sd | t | Horizons (64/256/720) | Verdict |
|---|---|---|---|---|---|---|---|---|
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 5.0, "size_min": 0.5}}` | j100sz05 | [0, 1, 2] | -0.28%, +1.00%, +0.23% | +0.32% | +0.64% | 0.86 | +1.21% / +0.20% / -0.46% | **INCONCLUSIVE** |
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 2.5, "size_min": 0.25}}` | jsz025 | [0, 1, 2] | +0.20%, +0.63%, -0.24% | +0.19% | +0.44% | 0.77 | +1.30% / -0.13% / -0.59% | **INCONCLUSIVE** |
| `{"v2_quant.json": {"rate": 0.5}}` | q50 | [0] | +0.14% | +0.14% | — | — | +0.17% / +0.18% / +0.07% | **INCONCLUSIVE** |
| `{"v2_dock.json": {"replace_rate": 0.6}}` | dr60only | [0, 1, 2] | -0.15%, +0.29%, -0.40% | -0.09% | +0.35% | -0.44 | -0.02% / +0.02% / -0.27% | **INCONCLUSIVE** |
| `{"v2_pool2.json": {"rate": 0.25}}` | p2_25 | [0] | -0.50% | -0.50% | — | — | -0.08% / -0.33% / -1.08% | **INCONCLUSIVE** |
| `{"v2_mix.json": {"rate": 0.3}}` | mix30 | [0] | -0.81% | -0.81% | — | — | -0.56% / -1.20% / -0.68% | **INCONCLUSIVE** |
| `{"v2_history.json": {"rate": 0.55}}` | h55 | [0] | -2.90% | -2.90% | — | — | -3.86% / -2.63% / -2.23% | **INCONCLUSIVE** |

## Per-domain effect (mean log MASE arm/reference across seeds; negative = better)

- **j100sz05**: transport -0.024, econ_fin -0.017, nature -0.005, sales -0.003, energy +0.006, web_cloudops +0.006, healthcare +0.011
- **jsz025**: transport -0.023, econ_fin -0.012, sales -0.007, nature -0.005, energy +0.009, web_cloudops +0.009, healthcare +0.013
- **q50**: web_cloudops -0.013, healthcare -0.011, sales -0.001, econ_fin +0.002, energy +0.002, transport +0.003, nature +0.008
- **dr60only**: econ_fin -0.003, healthcare -0.003, web_cloudops -0.003, energy -0.001, transport -0.001, nature +0.003, sales +0.006
- **p2_25**: web_cloudops -0.015, healthcare -0.002, transport -0.002, energy +0.005, sales +0.010, econ_fin +0.011, nature +0.021
- **mix30**: energy -0.002, transport -0.001, healthcare +0.001, nature +0.003, web_cloudops +0.004, econ_fin +0.009, sales +0.011
- **h55**: healthcare +0.000, energy +0.010, web_cloudops +0.021, econ_fin +0.031, sales +0.048, transport +0.048, nature +0.050

## Excluded

- `grid_gpu2@20261031T021943Z`: invalid: equal_steps
- `grid_gpu2s1@20261031T021943Z`: invalid: equal_steps
- `grid_gpu4@20261031T021943Z:jcombo`: multi-feature (3 switches differ)
- `grid_gpu4@20261031T021943Z:jsz05dr60`: multi-feature (2 switches differ)
- `grid_gpu4@20261031T021943Z:jsz05sing`: multi-feature (2 switches differ)
- `grid_gpu4s1@20261031T025733Z:j30sz05dr60`: multi-feature (2 switches differ)
- `grid_gpu4s1@20261031T025733Z:jsz025dr60`: multi-feature (2 switches differ)
- `grid_gpu4s1@20261031T025733Z:jsz05dr60`: multi-feature (2 switches differ)
