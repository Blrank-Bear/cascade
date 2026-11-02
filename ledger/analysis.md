# Experiment ledger analysis (feature by feature)

Rules: ADOPT-CANDIDATE needs ≥3 seeds, every seed > 0, t ≥ 2.5, no horizon below −0.5%. Only valid records and single-feature arms are used.

| Feature (switch vs reference) | Arm | Seeds | Per-seed gain | Mean | sd | t | Horizons (64/256/720) | Verdict |
|---|---|---|---|---|---|---|---|---|
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 5.0, "size_min": 0.5}}` | j100sz05 | [0, 1, 2, 3, 4, 5, 6, 7] | -0.28%, +1.00%, +0.23%, +0.68%, +0.64%, -0.43%, -0.10%, +0.34% | +0.26% | +0.50% | 1.46 | +1.37% / -0.05% / -0.55% | **INCONCLUSIVE** |
| `{"v2_jumps.json": {"max_outliers": 0.25, "max_shifts": 24.0, "rate": 1.0, "size_max": 2.5, "size_min": 0.25}}` | jsz025 | [0, 1, 2, 3, 4, 5, 6, 7] | +0.20%, +0.63%, -0.24%, +0.70%, +0.44%, -0.52%, -0.66%, +0.42% | +0.12% | +0.53% | 0.65 | +1.36% / -0.32% / -0.69% | **INCONCLUSIVE** |
| `{"v2_quant.json": {"rate": 0.5}}` | q50 | [0, 1, 2, 3, 4, 5, 6, 7] | +0.14%, +0.13%, -0.08%, +0.34%, +0.23%, -0.19%, -0.14%, +0.02% | +0.06% | +0.18% | 0.85 | +0.07% / -0.04% / +0.13% | **INCONCLUSIVE** |
| `{"v2_quant.json": {"rate": 1.0}}` | q100 | [0, 1, 2] | -0.11%, +0.32%, -0.29% | -0.03% | +0.31% | -0.16 | +0.01% / +0.01% / -0.11% | **INCONCLUSIVE** |
| `{"v2_pool2.json": {"rate": 0.25}}` | p2_25 | [0, 1, 2] | -0.50%, +0.61%, -0.36% | -0.08% | +0.60% | -0.23 | +0.11% / +0.17% / -0.53% | **INCONCLUSIVE** |
| `{"v2_dock.json": {"replace_rate": 0.6}}` | dr60only | [0, 1, 2] | -0.15%, +0.29%, -0.40% | -0.09% | +0.35% | -0.44 | -0.02% / +0.02% / -0.27% | **INCONCLUSIVE** |
| `{"v2_quant.json": {"rate": 0.75}}` | q75 | [0, 1, 2] | +0.13%, -0.30%, -0.21% | -0.13% | +0.22% | -0.99 | -0.14% / -0.12% / -0.13% | **INCONCLUSIVE** |
| `{"v2_stall.json": {"rate": 0.5}}` | stall50 | [0, 1, 2] | -0.17%, -0.02%, -0.52% | -0.24% | +0.25% | -1.63 | +0.39% / -0.48% / -0.62% | **REJECT** |
| `{"v2_stall.json": {"rate": 1.0}}` | stall100 | [0, 1, 2] | -0.01%, +0.08%, -1.65% | -0.53% | +0.97% | -0.94 | +0.67% / -0.86% / -1.40% | **INCONCLUSIVE** |
| `{"v2_mix.json": {"rate": 0.3}}` | mix30 | [0, 1, 2] | -0.81%, -0.06%, -1.48% | -0.79% | +0.71% | -1.92 | -0.51% / -0.96% / -0.89% | **REJECT** |
| `{"v2_history.json": {"rate": 0.55}}` | h55 | [0, 1, 2] | -2.90%, -1.11%, -3.03% | -2.35% | +1.07% | -3.79 | -3.54% / -2.04% / -1.48% | **REJECT** |

## Per-domain effect (mean log MASE arm/reference across seeds; negative = better)

- **j100sz05**: transport -0.032, econ_fin -0.012, nature -0.006, sales -0.002, web_cloudops +0.007, energy +0.008, healthcare +0.016
- **jsz025**: transport -0.027, econ_fin -0.008, sales -0.004, nature -0.004, web_cloudops +0.008, energy +0.010, healthcare +0.016
- **q50**: web_cloudops -0.003, healthcare -0.003, nature -0.002, econ_fin -0.001, energy +0.000, sales +0.000, transport +0.001
- **q100**: healthcare -0.007, web_cloudops -0.004, nature -0.001, econ_fin -0.000, energy +0.000, transport +0.004, sales +0.006
- **p2_25**: healthcare -0.004, web_cloudops -0.004, nature -0.001, sales +0.002, energy +0.002, econ_fin +0.003, transport +0.006
- **dr60only**: econ_fin -0.003, healthcare -0.003, web_cloudops -0.003, energy -0.001, transport -0.001, nature +0.003, sales +0.006
- **q75**: web_cloudops -0.007, healthcare -0.004, energy -0.001, econ_fin +0.001, transport +0.002, nature +0.003, sales +0.009
- **stall50**: transport -0.005, web_cloudops +0.002, nature +0.003, econ_fin +0.003, healthcare +0.004, energy +0.004, sales +0.007
- **stall100**: transport -0.011, econ_fin +0.002, nature +0.004, web_cloudops +0.006, energy +0.006, sales +0.010, healthcare +0.017
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
- `grid_gpu4s3@20261101T075944Z`: invalid: same_generator
