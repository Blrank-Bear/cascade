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

## Hold conditional and transfer proxy (chain metric), 2026-10-29
`tools/proxy/holds.py` gives P(exact-hold target | trailing constant run of the context) at h = 64. Cells are share of windows / P(hold).

| Set | P(hold) | run 0 | run 16–64 | run 64–256 | run 256–1024 | run ≥1024 |
|---|---|---|---|---|---|---|
| eval 10-24 | 0.066 | 0.71 / 0.002 | 0.04 / 0.30 | 0.04 / 0.68 | 0.02 / 0.86 | 0.006 / 0.89 |
| eval 10-25 | 0.059 | 0.72 / 0.001 | 0.06 / 0.28 | 0.03 / 0.71 | 0.02 / 0.78 | 0.004 / 1.00 |
| base corpus | **0.483** | 0.40 / 0.001 | 0.03 / 0.46 | 0.05 / 0.82 | 0.19 / 0.96 | 0.25 / 0.97 |
| flat stage | 0.278 | 0.60 / 0.000 | 0.02 / 0.33 | 0.02 / 0.71 | 0.09 / 0.97 | 0.17 / 0.96 |
| jumps 0.3 | 0.479 | 0.39 / 0.001 | 0.04 / 0.53 | 0.07 / 0.82 | 0.20 / 0.94 | 0.21 / 0.96 |

- **The king corpus is about 8× hold-heavy and over-confident in holds.** Under the log-floor metric that is close to optimal. A correct exact hold is worth about 18 log-units; a wrong hold costs only a naive-sized error. The break-even is roughly P(hold) > 0.5%.
- **The transfer proxy** (small CPU MLP; chain metric; trained per corpus; scored on 10-24 and 10-25 at h = 64) splits geomean MASE into hold and other windows:
  - **On other windows** every corpus beats naive (about 0.83 vs. 0.88), and corpora are within about 2% of each other.
  - **On hold windows** naive is exact (1e-9), base reaches 3.7e-4, flat 1.5e-3 and real-pool data 2.2e-3.
  - **The ranking is decided by hold precision:** jumps 0.2587 < quant 0.2625 ≈ base 0.2628 < mix 0.2653 < pool2 0.2632 < hist55 0.2694 < full stack 0.2718 < flat 0.2775 < real pool 0.2874.
- **Biggest headroom: hold precision.** Base is at 3.7e-4 on hold windows against 1e-9 for exact copying, worth about 2× on round MASE. Any stage that removes or perturbs hold segments should be treated as harmful until a GPU run says otherwise.

## Mild flat trimming is also harmful (2026-10-30)
- **Arms:** `v2_flat` with `keep_prob` 0.5 (fk50); the same with `tail` 1024 (fk50t1k); and jumps 0.3 + fk50.
- **Setup:** 4 seeds, chain metric, pools 10-24 and 10-25.

| Arm | Score | MASE on holds | MASE on others |
|---|---|---|---|
| j30 | **0.2613** | 2.65e-4 | 0.835 |
| base | 0.2641 | 4.01e-4 | 0.831 |
| j30 + fk50 | 0.2644 | 5.60e-4 | 0.830 |
| fk50t1k | 0.2651 | 5.75e-4 | 0.830 |
| fk50 | 0.2685 | 7.75e-4 | 0.830 |

- **Long flat tails drive hold precision.** Every trim of them worsens hold MASE roughly in proportion to how much flat content it removes. The small gain on other windows (≈0.001) doesn't pay for it.
- **Why jumps 0.3 works:** it adds mid-length hold runs and raises P(hold | run 4–64) from 0.14/0.46 to 0.19/0.53, so the corpus becomes more confident about holds, not less.
- **Next lever:** more exact holds inside dynamic channels (the `v2_holds` stage), not fewer flat tails.

## Stale-holds stage `v2_holds.json` is neutral (2026-10-30)
- **The stage:** exact sample-and-hold spans (4–512 points, ≤4 per 4096) in dynamic channels. Off by default; goldens unchanged.
- **Proxy, 4 seeds:**
  - holds 0.3: **0.2644**, holds 0.6: **0.2645** (base 0.2641);
  - jumps 0.3 + holds 0.3: **0.2616** (jumps 0.3 alone: 0.2613);
  - all within noise.
- **Why:** spans inside moving channels barely change the trailing-run profile of contexts (the holds table matches base to ±0.002).
- **What jumps 0.3 changes instead:** windows move from the 1024+ run bucket (0.252 → 0.213) into 64–256 (0.050 → 0.073). Level changes inside long flat (step-like) channels are what move the metric.
- **Follow-up:** jumps variants (rate 0.5, max_shifts 12, outliers off).

## Jumps variants, paired against base per seed (2026-10-30)
Seeds share initialisation across corpora, so per-seed differences are much tighter than raw scores. Tool: `tools/proxy/paired.py`.

| Arm (`v2_jumps.json`) | Mean d vs base | t (4 seeds) | Per-seed d |
|---|---|---|---|
| rate 0.3, max_shifts 12 (j30s12) | **−0.0038** | **−8.2** | −0.0030 / −0.0033 / −0.0037 / −0.0051 |
| rate 0.3, max_outliers 0.25 (j30no) | −0.0034 | −3.3 | |
| rate 0.5 (j50) | −0.0034 | −2.9 | |
| rate 0.3 (j30) | −0.0028 | −2.2 | one seed +0.0001 |
| holds 0.3 / 0.6, j30 + fk50 | ≈ 0 | < 0.5 | noise |
| fk50 | +0.0045 | +3.7 | worse |

- **More level shifts help; one-point outliers don't.** The best single setting is j30s12: about 1.4% better than base on every seed.
- **Next:** combine them (j50s12no, j30s24, j50s24no).

### Round 2 (combining)

| Arm | Mean d vs base | t | Hold MASE | Other MASE |
|---|---|---|---|---|
| rate 0.5, max_shifts 24, max_outliers 0.25 (j50s24no) | **−0.0072** | −5.4 | 1.70e-4 | 0.837 |
| rate 0.5, max_shifts 12, max_outliers 0.25 | −0.0049 | −2.4 | 2.31e-4 | 0.835 |
| rate 0.3, max_shifts 24 | −0.0041 | −7.4 | 2.43e-4 | 0.836 |
| base | 0 | | 4.01e-4 | 0.831 |

- **The gain is all hold precision.** Other-window MASE creeps up slightly (+0.006).
- **Round 3** looks for where the trend turns: rate 0.7, max_shifts 48.

### Round 3 (where does it turn?)

| Arm | Mean d vs base | t | Hold MASE | Other MASE |
|---|---|---|---|---|
| rate 0.7, max_shifts 24, max_outliers 0.25 (j70s24no) | **−0.0083** | **−12.0** | 1.51e-4 | 0.837 |
| rate 0.7, max_shifts 48 | −0.0079 | −8.4 | 1.46e-4 | 0.836 |
| rate 0.5, max_shifts 48 | −0.0064 | −9.2 | 1.81e-4 | 0.836 |

- **Shift count saturates at about 24.** Rate is still improving at 0.7.
- **Other-window MASE is flat** at about 0.837 across these arms.
- **Round 4:** rate 0.85 / 1.0 at 24 shifts, and 36 shifts at rate 0.7.

## Why early v2 training steps are slow on the 4090 (2026-10-30)
- **Measured:** 28m preset, 10 steps in 476 s (about 47 s/step), GPU at 100%.
- **Profile of one step:** `aten::add_` 20.7 s (55% of GPU time) + `aten::fill_` 13.3 s (35%); matmuls only about 1 s.
- **Cause** (upstream `cascade/trainer/pyramid_model.py:304-315`):
  - When the router is collapsed (`cap * E > 2 * N * K`), the MoE layer falls back to a Python loop over experts with `x @ weight[expert]`.
  - The backward of `weight[expert]` materialises a zero-filled gradient the size of the whole `(E, d, h)` expert tensor and adds into it, once per expert.
  - At random init the router is unbalanced, so the first steps take this path.
  - `route_bias` should rebalance it, after which the batched `bmm` path applies.
- **Upstream code:** validators run the same code; we do not patch it.
- **Open question:** what the steady-state step time is. A 30-min run with a per-step heartbeat (`.claude-work/tmp/step_clock.py`, which wraps `combine_gradients`) is measuring it.

### Round 4 (rate)

| Arm (max_shifts 24, max_outliers 0.25) | Mean d vs base | t | Hold MASE | Other MASE |
|---|---|---|---|---|
| rate 1.0 (j100s24no) | **−0.0112** | **−16.3** | 1.02e-4 | 0.838 |
| rate 0.85 | −0.0104 | −9.3 | 1.24e-4 | 0.837 |
| rate 0.7 | −0.0083 | −12.0 | 1.51e-4 | 0.837 |
| rate 0.7, max_shifts 36 | −0.0082 | −7.6 | 1.46e-4 | 0.837 |

- **The gain is monotone in rate up to 1.0,** i.e. every king row gets shifts.
- **Other-window MASE creeps up** (0.831 → 0.838). Watch for over-fitting to holds; this needs GPU confirmation.
- **Round 5:** shift size (1–10 and 10–100 median steps) and max_shifts 12, at rate 1.0.

### Round 5 (shift size, at rate 1.0)

| Arm | Mean d vs base | t | Hold MASE | Other MASE |
|---|---|---|---|---|
| size 1–10, max_shifts 24 (j100sz1) | **−0.0141** | −12.2 | 8.6e-5 | **0.834** |
| size 3–30, max_shifts 12 | −0.0115 | −16.4 | 1.11e-4 | 0.834 |
| size 3–30, max_shifts 24 | −0.0112 | −16.3 | 1.02e-4 | 0.838 |
| size 10–100, max_shifts 24 | −0.0091 | −6.6 | 1.03e-4 | 0.844 |

- **Smaller shifts win on both axes:** better hold precision, and a smaller other-window penalty.
- **Large shifts hurt other windows.**
- **Round 6:** size 0.5–5; size 1–10 with 12 and with 48 shifts.
- **Steady state does not improve** (2026-10-30): a 30-min run stayed at about 50 s/step through step 35. The router never left the collapsed path.
- **Screening patch** `tools/duel/fast_moe.py` (used via `duel_fast.py` / `grid_fast.py`): splits the expert weights with `unbind(0)` once per forward.
  - **Bitwise identical** final weights after 3 steps vs the original. The original is itself bitwise reproducible run-to-run.
  - **Speed:** 3-step wall time 166 s → 99 s. Steady-state s/step is being measured.
- **Steady-state step times on the 4090, 28m preset:**

| Setup | s/step |
|---|---|
| upstream code, 8 micro-batches | ≈ 50 |
| `fast_moe` patch, 8 micro-batches | ≈ 25.5 |
| `fast_moe` patch, 2 micro-batches (`--set micro_batches=2`, 22.6 GB VRAM) | **≈ 8.4** |

  - The micro-batch count is designed to leave the maths unchanged (full-batch load counts, global gradient combine). It's not bitwise identical, but every grid arm uses the same config, so comparisons stay paired.
- **First GPU grid** (`.claude-work/grid_gpu1` on the server):
  - Arms: base / j30 / j100sz1.
  - Budget `--hours 0.1` (≈ 795 steps, ≈ 2 h per arm).
  - Scoring: 3 pools × 2 round seeds, 2,000 windows.

### Round 6 (converged)
- **size 0.5–5:** −0.0130 (t −29, the most consistent); other-window MASE 0.832, ≈ base.
- **size 1–10 with max_shifts 12:** −0.0118.
- **size 1–10 with max_shifts 48:** −0.0108.
- **Optimum:** rate 1.0, max_shifts 24, max_outliers 0.25, size 0.5–10.

**CPU-proxy recommendation:**
- `v2_jumps.json` = `{"rate": 1.0, "max_shifts": 24, "max_outliers": 0.25, "size_min": 1, "size_max": 10}`: −0.0141 vs base (≈ 5.3%), better on every seed.
- Runner-up: size 0.5–5 (lower other-window cost).
- **This is CPU-proxy evidence only.** GPU confirmation arms are in `tools/duel/arms_jumps.json`.

## Numerics guard `v2_safe.json`, on by default (2026-10-30)
- **The bug:** GPU grid 1's base arm diverged at step 49 with a non-finite joint loss. On chain that is a burned submission.
- **Cause:** the trainer's causal scale is an expanding std floored at 1e-5. Channels that start exactly constant around 1e12 then change give truth ≈ 1e17. The energy-score float32 norm overflows at about 3e18.
- **Measured:** 0.6% of channels exceed 1e15; worst 8.9e16 (base) and 1.7e17 (jumps). A 12M-channel training run reaches the overflow (`tools/proxy/numerics.py`).
- **Fix:** recompute the trainer's statistics in numpy and divide by 10^k any channel above 1e12.
  - Matches upstream within 7.6e-6 relative on 3,000 channels; same flags 3000/3000.
  - After the fix the worst channel is 9.9e11; none zeroed; hold pattern preserved.
- **Regression checks:**
  - Inner goldens unchanged.
  - With the guard switched off, output is identical to the old v2 goldens; v2 goldens re-recorded with it on.
  - Validator OK; VmPeak 1,297 MB.
- **On GPU:** grid 2's base arm trained past the old failure point without diverging.

## Dock / traffic family `v2_dock.json` (off)
- **Target:** transport, the only domain worse than naive (log MASE +0.019, log WQL +0.052 with j100sz1); mostly GBFS bike-dock status plus 5-min road counts.
- **Fit:** the family matches eval transport statistics.
- **Transport improves:** with j100sz1, dock 10% takes transport to +0.001 / +0.029; econ_fin, nature and 1-min data improve too.
- **Overall it is worse:** 0.2533 (10%) and 0.2536 (5%) vs 0.2500. Hold MASE 1.2e-4 vs 8.6e-5; other MASE 0.836 vs 0.834.
- **Likely reason:** inserted rows displace hold-rich king rows from the fixed record budget. Kept off.
- **Replace mode** (`replace_rate`, which swaps dynamic king rows with hold share < 0.2):

| Arm | Score | Hold MASE | Other MASE |
|---|---|---|---|
| j100sz1 + replace 0.6 (jdr60) | **0.2481** | 5.5e-5 | 0.839 |
| j100sz1 + replace 0.3 | 0.2506 | — | — |
| j100sz1 | 0.2500 | 8.6e-5 | 0.834 |

  - jdr60 vs j100sz1 per seed: −0.0021 / −0.0027 / −0.0020 / −0.0005.
  - **The gain comes from more hold content, not transport** (transport WQL got worse). Other-window MASE rises.
  - The proxy may over-reward holds, so jdr60 is queued as a GPU arm in grid 2.

## First GPU confirmation, grid 2 (2026-10-30)
- **Setup:**
  - Model: 28m preset, `--hours 0.1` (≈ 795 steps), 2 micro-batches, `fast_moe` patch (bitwise identical).
  - Numerics guard on.
  - Scoring: 3 pools × 2 round seeds, 2,000 windows, margin 0.01.

| Arm | Wins | Mean gain vs base | Per-cell gain | Horizons |
|---|---|---|---|---|
| **j100sz05** (rate 1.0, 24 shifts, outliers 0.25, size 0.5–5) | **6/6** | **+2.69%** | +2.02 … +3.48% (LCB +0.0136 … +0.0280) | all positive: h64 +2.6…5.2%, h256 +1.6…3.1%, h720 +1.0…2.4% |
| j100sz1 (size 1–10) | 5/6 | +2.30% | +1.53 … +3.21% | all positive |

- **j100sz05 passes the promotion rule** (≥ 5/6 cells, same sign at every horizon).
- **The GPU prefers smaller shifts,** consistent with sz05's lower other-window cost on the proxy.
- **Replace sweep on CPU** (vs j100sz1): rate 0.8 +0.0021, rate 1.0 +0.0011, cut 0.1 −0.0005. jdr60's −0.0018 looks like noise (non-monotone), so replace mode stays off. jdr60 is still on the GPU queue as a check.
- **CPU sweep around sz05** (paired vs j100sz05):
  - size 0.25–2.5: **−0.0017** (all 4 seeds better);
  - 12 shifts: +0.0037; 48 shifts: +0.0024. 24 shifts is optimal.
  - jsz025 is queued on the GPU (grid 2 work dir) before the long-budget grid 3.
  - Next on CPU: sizes 0.1–1 and 0.15–1.5, and size 0.25–2.5 with outliers at the default rate.
- **GPU, jdr60** (j100sz1 + dock replace 0.6): **6/6, mean +2.54%**. It beats j100sz1 (+2.30%) in every cell by +0.15 to +0.35 points, but that is one training seed and the cells are correlated.
  - So the GPU shows a small consistent gain that the CPU proxy called noise.
  - jsz05dr60 (sz05 + replace 0.6) is added to the grid 2c queue.
- **Smaller shifts on CPU** (vs j100sz05): 0.25–2.5 **−0.0017**; 0.1–1 +0.0006; 0.15–1.5 +0.0014; outliers at the default rate are neutral. The CPU optimum is size ≈ 0.25–2.5 with 24 shifts.
- **Throughput and memory** (1 pinned core, RLIMIT_AS 2048 MB; v2 needs 289k values/s):

| Config | values/s | × requirement | VmPeak |
|---|---|---|---|
| j100sz05 | 1.50M | 5.2× | 1,358 MB |
| jsz025 | 1.39M | 4.8× | 1,304 MB |
| jsz05dr60 | 1.23M | 4.2× | 1,400 MB |

- **Group policy** (GPU only; the CPU proxy is univariate): a `jsz05sing` arm (sz05 + singleton groups) is added to grid 2c.

## GPU replication on training seed 1 (grid `grid_gpu2s1`)

| Arm | Seed 0 | Seed 1 |
|---|---|---|
| **j100sz05** | 6/6, +2.69% | **6/6, +3.87%** (LCB +0.029 … +0.036; every horizon positive: h64 +4.8…6.1%, h256 +3.2…4.2%, h720 +1.9…3.5%) |
| j100sz1 | 5/6, +2.30% | 2/6, +1.77% |

- **j100sz05 is the confirmed leader** at the 28m / 0.1 h screening scale: 12/12 cells across two training seeds.
- Still to run: grid 2c (jsz025, jsz05dr60, jsz05sing), then the long-budget grid 3 (base vs j100sz05 at 0.25 h).
- **h=256 transfer proxy** (`tools/proxy/transfer_h.py --horizon 256 --ctx 1024`), paired vs base:
  - j100sz1 −0.0083, jdr60 −0.0074, j100sz05 −0.0055, jsz025 −0.0034.
  - Every jumps arm beats base, but the ranking is the reverse of the GPU (sz05 > sz1).
- **Conclusion:** the CPU proxy is reliable for direction (jumps help, flat trimming hurts) but not for ranking close variants. Fine-tuning is done on GPU.
- **Large numerics scan of real generator output** (j100sz05, 4 seeds incl. 2^63−1, 3,200 records each = 409,600 channels, upstream causal_standardize):
  - **Without the guard** (a stale pre-guard copy): max |truth| reached **1.48e18**, about half the overflow. With jumps on every record the guard is essential.
  - **With the guard** (current generator): max |truth| = 1.0e12 (the limit), 0 non-finite channels.
- **Re-measured with the guard:**

| Config | values/s | × requirement | VmPeak | Validator |
|---|---|---|---|---|
| j100sz05 | 1.29M | 4.5× | 1,388 MB | OK |
| jsz05dr60 | 1.29M | 4.4× | 1,367 MB | OK |

  - The earlier perf and validator numbers for the candidates came from pre-guard copies.
- **Process rule:** refresh `.claude-work/tmp/gen_*` from `generator/` before any check (the grid already copies fresh files every run).
- **Where j100sz05 gains on GPU** (`tools/duel/breakdown_scores.py`; mean log arm/base, seed 0 / seed 1; negative = better):

| Domain | log MASE (s0 / s1) | log WQL (s0 / s1) |
|---|---|---|
| transport | −0.039 / −0.045 | −0.048 / −0.043 |
| nature | −0.038 / −0.051 | −0.062 / −0.063 |
| econ_fin | −0.024 / −0.064 | −0.044 / −0.070 |
| sales | −0.014 / −0.024 | −0.029 / −0.034 |
| energy | −0.012 / −0.012 | −0.040 / −0.039 |
| web_cloudops | +0.001 / −0.020 | −0.017 / −0.024 |
| healthcare | **+0.010** / −0.015 | 0.000 / −0.015 |

  - **Horizons:** h64 −0.036 / −0.054, h256 −0.014 / −0.032, h720 −0.005 / −0.020.
  - **Top sources:** coinbase_spot_15m (−0.075 / −0.197), metar_us_airports, gbfs bike stations, usda hogs, energia_jp.
  - **Healthcare** is the only domain without a clear gain: a candidate target.
- **GPU queue (2026-10-30 14:10):**
  1. grid 2c (jsz025, jsz05dr60, jsz05sing);
  2. benchmark gate (base vs j100sz05; GIFT-Eval / BOOM / TIME) or grid 3 first, depending on the data download;
  3. grid 2d (sz05 with 12 / 48 shifts, rate 0.7).

## GPU grid 2c (seed 0, same work dir)

| Arm | Wins | Mean gain vs base |
|---|---|---|
| jsz05dr60 (sz05 + dock replace 0.6) | 6/6 | **+3.82%** |
| jsz025 (size 0.25–2.5) | 6/6 | **+3.81%** |
| jsz05sing (sz05 + singleton groups) | 6/6 | +3.35% |
| j100sz05 | 6/6 | +2.69% |
| jdr60 | 6/6 | +2.54% |
| j100sz1 | 5/6 | +2.30% |

- **The gains over sz05 (+0.7 to +1.1 points) are about the size of seed-to-seed spread** (sz05 was +2.69% on seed 0 and +3.87% on seed 1), so they need replication.
- **Queue rebuilt** as `chain` on the server:
  1. grid 2e, seed 0: jsz025dr60, jsz025sing, jcombo (size 0.25–2.5 + dock replace 0.6 + singleton groups);
  2. grid 2s1e, seed 1 replication: jsz025, jsz05dr60, jsz05sing, jcombo;
  3. grid 2d: sz05 with 12 / 48 shifts, rate 0.7;
  4. the benchmark gate runs between steps once its data download has finished.
- **The long-budget grid 3 was stopped;** it will be rerun with the final candidate.
- **Process note:** never `pkill -f` a pattern that appears in the ssh command itself. That killed the session mid-update (GPU idle about 2 min).

## CORRECTION: all GPU grids so far were wall-clock-bound, so step counts differ
- **What happened:** `for_hours(0.1)` sets 795 steps but guard = max(1.0 × 0.1 h, `heat_guard_floor_seconds` 900 s). At 8.4 s/step every arm stopped at the 900 s deadline.
- **The effect:** base trained only 115–117 steps vs 123–134 for the jumps arms (~10–15% more). Part of the measured +2.3…3.9% may be extra training. Grids 2, 2s1 and 2c are **confounded**.
- **Fix:** `chain.v2-28m-mb2-steps.toml` sets `[round] heat_guard_factor = 30`, so the step budget binds. `--hours 0.05` gives 397 steps per arm (~56 min each).
- **Re-run:** `grid_gpu4` (seed 0) and `grid_gpu4s1` (seed 1) with base, j100sz05, jsz025, jsz05dr60, jsz05sing, jcombo. Check `n_series/16` is equal across arms.

## Equal-steps GPU result (grid 4, seed 0, 396 steps every arm): the jumps gain was mostly the confound

| Arm | Wins | Mean vs base | h64 | h256 / h720 |
|---|---|---|---|---|
| **jsz05dr60** (sz05 + dock replace 0.6) | 0/6 | **+0.75%** (LCB −0.003 … +0.005) | +1.0…3.0% | ≈ 0 |
| jsz025 | 0/6 | +0.20% | +0.8…1.9% | slightly negative |
| j100sz05 | 0/6 | −0.28% | +0.2…1.3% | −0.5…−1.5% |
| jsz05sing | 0/6 | **−0.98%** | mixed | negative |
| jcombo | 0/6 | **−0.93%** | mixed | negative |

- **The earlier +2.3…3.9% (grids 2/2s1/2c) came mostly from the extra training steps** the jumps arms got under the 900 s wall clock.
- **At equal steps:**
  - jumps help h=64 (holds) but hurt h=256/720; net ≈ 0;
  - dock replace 0.6 is the only mildly positive change;
  - singleton groups are harmful.
- **None meets the 1% LCB bar.** No current variant is a submittable improvement over the king's code.
- **The CPU proxy (h=64 only) over-rewarded hold precision.** Its h=256 run did agree that the gains shrink with horizon.
- **Next seed-1 grid** (`grid_gpu4s1`): base, jsz05dr60 (replication), dr60only, j30sz05dr60, jsz025dr60.

## Benchmark gate risk (2026-10-31)
- **Setup:** upstream `evaluate_bench_gate` (v2 rule) on jsz05dr60 vs base, grid 4 seed-0 checkpoints, GIFT-Eval / BOOM / TIME.
- **Ratios are fine:** avg 0.989, worst LCB 0.991.
- **It fails on task win rate:** **0.448 < 0.5** (GIFT 0.41, TIME 0.38, BOOM 0.55). The hold-oriented corpus changes win BOOM tasks but lose most GIFT/TIME tasks.
- **Consequence:** feature evaluation must include the bench gate, and FEV must be set up for the real 4-suite rule.
- **4-suite gate (diagnostic, FEV 65 univariate tasks):** jsz05dr60 vs base **fails, win rate 0.459** (GIFT 0.41, BOOM 0.56, TIME 0.38, FEV 0.49). Average ratio 0.991 is better than base, but the gain is narrow: it wins BOOM-like ops tasks and loses most GIFT/TIME tasks.

## Where the trained model's error mass is (base, seeds 0–2, 35,964 windows; `tools/ledger/error_sources.py`)
- **Worst sources by log MASE:**
  - GBFS / citybikes **bike-station status** (transport): mean log MASE +2.4 … +9.5.
  - Socrata **"*_daily_volume"** open-data counts (sales, healthcare): log MASE +2.5 … +6; MASE > 1 on 100% of their windows.
- **Daily-volume windows are unfixable by data:** every arm gives an identical MASE (delta 0.000). The history is constant and the target departs from it, so all models output the same forecast.
- **Bike stations respond to data** (`tools/ledger/source_deltas.py`):
  - jumps: Taipei −0.27, Swiss e-cargo −0.22, Ottawa −0.14, Basque −0.12 log MASE vs base;
  - dock replace: e-cargo −0.36;
  - Bratislava gets worse with every arm.
  - Mean over the top-25 error sources: jumps −0.058, dock −0.035, quant +0.003, pool2 +0.017.
- **The fixable error mass is "long constant stretch then movement" (bike stations).** Jumps target exactly this, which is why they help h=64.

## Stall-break stage `v2_stall.json`: rejected (2026-11-01, 3 seeds, equal steps)

| Arm | Seeds 0 / 1 / 2 | Mean | h64 / h256 / h720 | Verdict |
|---|---|---|---|---|
| rate 0.5 | −0.17 / −0.02 / −0.52% | −0.24% | +0.39 / −0.48 / −0.62% | **REJECT** |
| rate 1.0 | −0.01 / +0.08 / −1.65% | −0.53% | +0.67 / −0.86 / −1.40% | negative (inconclusive) |

- **Restricting level changes to stalled channels does not avoid the long-horizon cost.** Every "levels can change" feature (jumps 0.5–5, jumps 0.25–2.5, stall breaks) trades better h=64 and transport for worse h=256/720 and other domains; net ≈ 0 or negative.
- **Treat this as a property of the model and metric:** more level-change content makes the model less persistent at long horizons.
- **Ledger status after 5 seeds:**
  - jumps 0.5–5: +0.46%, t 2.07;
  - jumps 0.25–2.5: +0.35%, t 2.02;
  - quant 0.5: +0.15%, t 2.17, positive at all horizons.
  - All INCONCLUSIVE (one negative seed each).
  - Rejected: history 0.55, mix 0.3, stall 0.5. Neutral: pool2, dock replace.
- **None of these features can approach the chain's 1% LCB bar.**

## Quant dose test (2026-11-02, 3 seeds, 396 equal steps, 28m mb2)

| rate | seeds | per-seed | mean | t |
|---|---|---|---|---|
| 0.5 | 5 | +0.14 +0.13 -0.08 +0.34 +0.23 | +0.15% | 2.17 |
| 0.75 | 3 | +0.13 -0.30 -0.21 | -0.13% | -0.99 |
| 1.0 | 3 | -0.11 +0.32 -0.29 | -0.03% | -0.16 |

No dose response: raising quantization above 0.5 removes the small gain. If quant is kept, 0.5 is the
ceiling. All three INCONCLUSIVE by the fixed rules; none near the chain's 1% bar.
Seeds 5 and 6 for jsz05 / jsz025 / q50 are running next (grid_gpu4s5, grid_gpu4s6).

## Why h=720 does not move with generator changes (2026-11-02)

- longrw30, lseason30 (seed 0) and the 3-seed error budget: the largest excess error is h=720,
  but neither family moved it (longrw30 h720 -0.83%, lseason30 -0.11%) while they gained +1-4% at
  h=64/256 in transport and econ_fin (ledger/breakdowns/*_seed0_cells.txt).
- Cause is in the pinned training contract: CPM masks spans of 1..cpm_c_max=16 patches of
  patch_size=32 (<=512 steps); an h=720 forecast is 23 masked patches at the end, decoded in one
  pass (STABLE_DECODE_STEPS 768). Depths 17-23 patches are almost never trained.
- The only generator-side lever (a per-row "mask" field: masked input, loss on the first patch
  after a gap) is not available: v2 [training] accepted_fields = ["groups"] only.
- The king has the same limit, so h=720 is not where the duel is decided. Strategy: maximise
  h=64/256 gains in the domains that respond (transport, econ_fin), and stop the losses elsewhere
  (matched replacement instead of random replacement).
