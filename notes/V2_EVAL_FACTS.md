# v2: what the trainer and the eval actually see (checked in upstream code, 2026-10-29)

These facts drive the switchable v2 stages in `generator/generator.py`, and they say what the GPU screening should test.

## Training (`[v2.training]` in `upstream/chain.toml`, `cascade/trainer/pyramid_trainer.py`)
- **Recipe:** `cascade_pyramid` (`cascade-moe-v2-120m`), with patch 32, context 4096 (128 patches) and 23,841 steps.
- **Batches:** `batch_size = 512` sequences, so each step is 16 records of 32 channels. The 50e9-point corpus is seen about **once**, as about 381k records.
- **Cropping:** `long_series = "crop"`. A record longer than 4096 is cut into stratified 4096 windows, and billing still counts every point, so longer records buy nothing.
- **Losses:** a marginal pinball loss plus a copula **energy score** (`copula_patches = 127`). Both receive `groups`, so attention and the joint loss stay within a group.
- **Masking:** contiguous patch masks on the context (c_max 16, p_max 0.4).

## Eval (`cascade/trainer/pyramid_wrapper.py`, `cascade/validator/evaluator.py`)
- Every window goes through `forecast_joint(history, horizon, num_samples)` with **`groups=None`**.
- **History padding:** a history shorter than 4096 is **left-padded with its first value** (`_prep`). This is the same pad the v2 packer uses for short rows.
- **Eval contexts are short** (v2 ladder, 4,000 windows, 2026-10-23 and 10-25 snapshots; `.claude-work/tmp/ctx/eval_ctx.py`):

  | Effective history | ≤128 | 128–256 | 256–512 | 512–1024 | 1024–2048 | 2048–3072 | >3072 |
  |---|---|---|---|---|---|---|---|
  | Eval windows | 2.4% | 4.9% | 12.1% | 16.5% | 19.5% | 9.0% | 35.6% |
  | Current corpus (mix off) | 4.3%* | 0.2% | 3.7% | 14.0% | 11.4% | 10.8% | 55.6% |

  \* These are almost entirely flat channels, not short real histories.

  The eval median is about 1,640 points; the corpus median is about 3,500.
- **Channel counts:** about 89–91% of windows are univariate (C = 1). About 10% have C = 2–7 and are forecast jointly, as one group, because `groups=None`.

## Coverage proxy (`tools/proxy`, base corpus vs. the 3 newest snapshots, pad stripped)
- Classifier AUC is 0.927, so the corpus is easy to tell apart from real pool data. The largest gaps:
  - **Integer values:** over half the pool is integer-valued (int_frac median 1.0); the corpus median is 0.10.
  - **Noisy series:** the pool has many more noisy, low-autocorrelation series. acf1 q25 is 0.47 in the pool vs. 0.81 in the corpus; spectral entropy q75 is 0.84 vs. 0.63.
  - **Relative spread:** the pool's CV is higher (log10 CV median −0.21 vs. −0.43).
  - **Flat channels:** about 12% of synthetic channels are constant over pool-length tails. The pool builder drops such series (`min_std`).
- **Worst-covered pool domains:** econ_fin and web_cloudops. The best covered is nature.

## Switchable stages added for these gaps (all off by default; default output byte-identical)
| File in config dir | Stage | Gap it targets |
|---|---|---|
| `v2_history.json` `{"rate": r}` | history match: a row keeps its last k steps (k from the eval distribution) and the rest is a first-value pad | short eval contexts |
| `v2_pool.json` `{"rate": r}` | pool-match families: Poisson/NB seasonal counts, intermittent counts, rounded noisy measurements, tick-rounded walks | integer-valued, noisy, high-CV series |
| `v2_groups.json` `{"policy": "row"/"singleton"/"joint"/"mixed"}` | group labels per record | train/eval attention match (eval is univariate, or joint over all channels) |
| `v2_mix.json` `{"rate": r}` | (earlier) KernelSynth / trend × seasonal / multi-seasonal AR | broad dynamics for random init |

These are hypotheses. The proxy only says the corpus looks more like the pool; GPU duels decide whether that scores better.

## CPU results for the new stages (2026-10-29, 2 seeds × 400 records, 8 channels per record)
- Validity: `tests/v2/validate.py`, 2 seeds × 150 records.
  - The history, pool, all-stages (mix 0.3 + pool 0.25 + history 1.0) and singleton/mixed/joint group configs all pass.
  - All are deterministic, with no duplicates and max |corr| ≤ 0.998.

| Config | Proxy AUC | Notable KS change vs. base | Effective-history median (eval 1,643) |
|---|---|---|---|
| base | 0.927 | — | 3,496 |
| mix 0.3 | (0.953 with pad kept) | int_frac worse | 3,571 |
| pool 0.25 | 0.932 | spectral entropy 0.235 → 0.198, int_frac 0.187 → 0.151, acf1 0.153 → 0.110, trend 0.112 → 0.089 | — |
| history 1.0 | 0.933 | — | 919 (overshoots) |
| **history 0.55** | — | — | **1,626**; >3072 bucket 34.6% vs. eval 35.6% |

- **Pool stage:** pool 0.25 closes the noise and integer gaps. Its own families are still separable on spike and kurtosis, so they are a first draft.
- **History rate:** history 0.55 matches the eval context distribution.
- **Suggested GPU screening grid (stage B):**
  - history {0, 0.55};
  - pool {0, 0.25};
  - mix {0, 0.3};
  - groups {row, singleton};
  - start with the 4 single-factor arms plus base.

## Pool-match v2 and flat-channel replacement (2026-10-29)
- **`v2_pool2.json` (rate 0.25):** persistent latent signal with heavy-tailed noise, outliers and rounding. Per-family medians now bracket the pool (acf1 0.83–0.97 for the signal families vs. 0.92 in the pool). Proxy AUC 0.922.
- **Flat channels:**
  - In king rows, 26% of channels are exactly constant over their last 512 points, and 52% of rows contain one (first 3,000 rows, seed 0).
  - Eval contexts end in a constant 512-point run only 1.7% of the time (64-point run: 5.5%).
- **`v2_flat.json` `{"enabled": true}`:** replaces flat king channels with pool2 series, keeping each one with `keep_prob` 0.07, which is about the eval rate. Proxy AUC **0.918**, the best single stage.
- **Interaction:** with flat on, flat channels no longer count as short histories, so the history rate must rise to about **0.75**.
  - flat + pool2 0.25 + history 0.75 gives a history median of 1,613 vs. eval's 1,643, with all buckets within about 3 points.
  - It passes validation, and golden is unchanged.
- **Stage-B arms** (`tools/duel/arms_stage_b.json`): base, hist55, pool2_25, flat, mix30, singleton, flat_pool2_hist75.

## Reporting-resolution quantization (2026-10-29)
- **Whole-series integer share:** pool 52.5% all-integer; base 44.0%; flat + pool2 + history 0.75 reaches 50.8%. A separate integerization stage is not needed.
- **`v2_quant.json` `{"rate": r}`:** rounds king channels to a nice tick (1/2/5 × 10^k) between 0.2× and 3× their median step.
  - With flat on and rate 0.6, KS drops for unique ratio (0.160 → 0.037), flat_frac (0.134 → 0.064) and int_frac (0.111 → 0.062), and the pool medians are matched.
  - AUC barely moves (0.918 → 0.917), because the classifier relies on diff kurtosis and spikes.
  - Rate 0.6 slightly overshoots flat_frac, so **0.5** is recommended.
- **Remaining largest gaps:** diff kurtosis and spikes are too low (the pool has jumps and outliers), the corpus is too periodic (seasonal_acf), and spectral entropy is too low.

## Jumps and outliers (2026-10-29)
- **`v2_jumps.json` `{"rate": r}`:** persistent level shifts plus one-step outliers on king channels, sized in median-step units. It is applied before quantization.
- **Rate 0.3** (with flat + quant 0.5): KS falls for diff kurtosis (0.216 → 0.167) and spikes (0.204 → 0.151); AUC 0.916.
- **Rate 0.6:** overshoots (flat_frac median 0.233 vs. 0.116, more trend); AUC 0.925. Use **0.3**.

## Proxy summary (pad-stripped AUC vs. 3 snapshots; lower = closer to the pool)
| Config | AUC |
|---|---|
| base | 0.927 |
| pool2 0.25 | 0.922 |
| flat | 0.918 |
| flat + quant 0.5 (0.6 measured) | 0.917 |
| flat + quant 0.5 + jumps 0.3 | **0.916** |

- **What the proxy can't do:** the remaining gaps (corpus too periodic, low spectral entropy, low CV) come from the king lineage's own dynamics, and they are past the point where post-hoc transforms help.
- **Diminishing returns:** further CPU gains will be small. The GPU grid is the real test.

## Negative result: additive observation noise (2026-10-29, not kept)
- Tested a white or AR(1) noise stage on king channels (noise std 0.02–0.8 × channel std), on top of flat + quant 0.5 + jumps 0.3.
- **Result:** proxy AUC 0.926 at rate 0.3 and 0.946 at rate 0.6, both worse than 0.916 without it. acf1_diff moves the wrong way.
- **Conclusion:** the pool's extra roughness is not additive measurement noise. The code was dropped before commit.

## IMPORTANT: exact holds dominate the round metric (checked in `cascade/eval/{mase,crps,scoring}.py`)
- **Round score:** sqrt(geomean per-window WQL × geomean per-window MASE), computed in log space with floors of **1e-12** (WQL) and **1e-9** (MASE). Windows with an all-zero target are masked out of WQL.
- **MASE definition:** mean |y − median forecast| / in-sample *seasonal*-naive MAE, with the seasonal period taken from the window metadata and the scale floored at 1e-9.
- **Exact-hold windows:** **3.1–3.7%** of eval windows (**6.6% at h = 64**) have a target exactly equal to the last history value. 14% of all target points equal the last value.
- **Leverage:** an exact or near-exact hold forecast on such a window is worth up to ln(1e8) ≈ 18 log-units of MASE. Over about 3.4% of windows that is about a 0.5× factor on geomean MASE, larger than any realistic modelling gain.
- **Consequences:**
  - The king lineage's heavy hold content (26% of channels constant over their last 512 points; `held_rate` 64%) is plausibly deliberate. It teaches confident, exact persistence.
  - **`v2_flat.json` (flat replacement) is risky.** It removes exactly that content. Its rationale (the pool builder drops constant *series*) does not hold at the window level. Keep it out of the default stack and let the GPU grid decide, using only the `flat` single arm.
  - The quantization stage creates ties and exact repeats, which may help here.
  - The feature proxy (AUC) is blind to this. The transfer proxy now uses the chain's metric and floors.
