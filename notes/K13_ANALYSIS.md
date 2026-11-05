# Reign-13 king (716765dc): strengths, weaknesses, our plan

Foundation since 2026-11-04: `generator/` = this king, refactored into our style:
- the atomic c268 stream with the exact c251 speed kernels;
- the king's v2 layers, split into atomic helpers.

Goldens are byte-identical to the unchanged king (`tests/golden/run_k13.sh`). The previous codebase is in `generator_c251/`.

## What the king is
- **Content.** Above its K0 banner it is c268, our old foundation's king (04e22672) line for line, minus the c251 speed kernels. No new series families.
- **Its whole edge is the v2 layer stack:**
  1. 32-channel first-fit packer (K0-32G), with the budget rescale from n.
  2. MAGGUARD: rows with peak > 1e4 are divided by a power of 10.
  3. Groups: SINGLETONS, then MVKEEP (10% of multichannel records keep their group). The SINGLETONS layer itself is dead code, because MVKEEP calls its parent directly.
  4. PADK-NEAR: a non-binary channel whose first move lies in the last 1024 points becomes exactly constant.
  5. LCP-LATE: at child yield 10,837 (the WSD cooldown, the last 1/11 of updates) seven hooks switch:
     - PKN back to 1536;
     - YM min n to 2560;
     - the C128 hydro mix;
     - the XA settings;
     - the MVK tag.
- **Dead code:** the K0 8-channel packer class is never reached, because 32G calls the c268 base directly.

## Strengths (keep)
- Contract-safe: assert-before-yield everywhere, canonical uint8 labels, finite float32-range values.
- The training-attention policy matches eval: about 88-90% of windows are univariate, and eval passes no groups.
- PADK-NEAR targets an exact eval situation: a z = 0 history (constant) followed by a move.
- A cooldown-phase curriculum keyed to the trainer's schedule: the final LR decay sees a shifted mix. This is the main novel lever.
- Throughput is ample: about 10 yields/s on one WSL core, against about 2.2/s needed per child.

## Weaknesses (address)
- **W1. The cooldown switch is an absolute yield (10,837).** It is right only for the production n, invisible in any shorter run, and fragile if the budget changes.
  - Fix: `lcpr`, a relative switch. It is byte-identical in production and fires at the screen's cooldown.
- **W2. Variate attention is almost untrained.** MVKEEP p = 0.1, and singletons give Q/K no gradient. The ~10% multichannel eval windows (C = 2-7, forecast jointly) get a near-uniform channel average.
  - Fix: tune `_MVK_P`. It is label-only, so values stay byte-identical.
- **W3. No content work.** The c268 content has our measured weak spots: h=720 seasonal domains, and econ_fin / transport long horizons.
  - Our overlays (ovlhalf: mean-reverting level overlay + amplitude overlay at 0.15 each) gained +0.59% over 5 seeds on the same c268 content, positive on 3 of 5 seeds.
  - Fix: port them as record-level layers (before packing, after PADK-NEAR; constant rows are untouched by construction).
- **W4. Only one curriculum switch.** The cooldown recipe is a hand-picked list of 7 hooks.
  - Untried: our content changes applied phase-wise, i.e. trunk only or cooldown only.
- **W5. Screening blind spots, ours not the king's.**
  - 28m / 396 steps; one seed has an SD of about 0.7%.
  - Rule from now on: every arm runs on at least 2 seeds before any verdict, and all arms are compared on the same seeds.

## Plan (one feature per commit, switchable, off by default)
1. `lcpr` (done, 8b0f4a9). The screening base = king + lcpr on, so the king's curriculum is active in the screen.
2. Calibration: k13 vs the old c251 base on seed 0, same windows. Does our screen see the king's advantage?
3. Port ovl (mrovl + amovl) as a record-level layer; test ovlhalf on k13.
4. MVK_P dose (0.1, then 0.3).
5. Phase-wise content: ovl in the trunk only, or in the cooldown only.

## Calibration (2026-11-04, grid_gpu4, seed 0, same 2000 windows)
- **k13 vs old base:**
  - k13 is the unchanged king, so its cooldown switch never fires in a 396-step run.
  - Round gain **+0.04%**, about equal. h64 -0.03%, h256 -0.09%, h720 +0.02%.
  - By domain: web +1.27%, econ_fin +0.67%, nature +0.45%, sales -1.82%, transport -1.11%.
- **ovlhalf (on the old base) vs k13:** +1.12% on the same seed.
- **Reading:**
  - In the screen, the king's label / PADK / magnitude layers net about zero against our c251 v2 base.
  - Its crowning edge, if any, is the cooldown curriculum, or effects that only appear at 120M / 23,840 steps.
  - Our content overlays are the measured lever. ovlhalf on k13 + lcpr (grid_k13 / grid_k13s1) is the deciding test.

## ovlhalf vs k13 + lcpr (grid_k13, seed 0, 2026-11-04)
- Base = king + lcpr on (the cooldown curriculum fires in the screen). Arm = base + ovl level_rate 0.15 + amp_rate 0.15.
- Round gain **+0.59%**. Per pool/round-seed: +0.30, +0.84, +0.52, +0.64, +0.69, +0.55. Positive on all 6.
- Cells (h × domain):
  - transport +2.17% (h64 +3.59, h256 +2.94);
  - econ_fin +1.51% (h256 +2.74);
  - health +0.10 (h720 -1.79);
  - nature -0.23;
  - energy, sales, web about 0.
- Reading:
  - vs the unchanged k13, the same overlays gave +1.12%. With lcpr the gap halves, so the king's cooldown curriculum is worth about 0.5% in our screen.
  - The overlays add about +0.6% on top. That is below the ~1% level bar.
  - Seed 1 is in progress.
- Next lever:
  - the overlays' gains sit in transport / econ_fin at h ≤ 256;
  - the losses are at h720 health / nature.

## k13 grid results (base = king + lcpr; 2026-11-04 15:25 UTC)

| arm | s0 | s1 | mean | h64 / h256 / h720 (s0) |
|---|---|---|---|---|
| ovlhalf (ovl 0.15 / 0.15, all phases) | +0.58 | +0.26 | +0.42 | +0.77 / +1.18 / -0.19 |
| mvk30 (MVKEEP p 0.3) | +0.20 | -0.01 | +0.10 | -0.01 / +0.57 / +0.04 |
| ovlcool (ovl in the cooldown only) | +0.45 | (queued) | | +0.18 / +0.62 / **+0.56** |

- **mvk30:** about zero over 2 seeds, i.e. within noise. Dropped as a lever; the king's p = 0.1 stays.
- **ovlhalf:** positive on both seeds, but only +0.42% mean. Its h720 is negative on both seeds (-0.19, -0.25).
- **ovlcool:** the only arm with a positive h720 so far.
  - This supports the hypothesis that all-phase overlays teach long seasonal records to drift.
  - Two fixes are queued as arms_k13d, after each lane's current queue:
    - ovs20: skip the overlays on seasonal records (the new `ovs` gate);
    - ovlshort: overlay half-lives capped at 700.

## Update 18:40 UTC: phase results
| arm | s0 | s1 | mean |
|---|---|---|---|
| ovltrunk (ovl before the cooldown only) | +0.72 | +0.45 (4/6 pools) | ~+0.6, best so far |
| ovlcool (ovl in the cooldown only) | +0.45 | -0.14 | ~+0.15; the s0 h720 gain did not replicate |
| ovlhalf (all phases) | +0.58 | +0.26 | +0.42 |

- **Reading:** the overlays help most when the king's cooldown runs on the clean c268 mix. Overlays in the trunk add robustness; the cooldown sharpens on the eval-like data.
- **Queue:** arms_k13d (all-phase gates) was dropped before it started training and replaced by arms_k13e, the same gates on trunk-phase overlays: ovs20t, ovlshortt. Both seeds.

## Update 23:17 UTC: gates on ovltrunk (arms_k13e)
| arm | s0 | s1 | mean |
|---|---|---|---|
| ovltrunk | +0.72 | +0.48 | **+0.60** |
| ovs20t (seasonal gate 0.2) | +0.45 | +0.51 | +0.48 |
| ovlshortt (half-lives <= 700) | +0.29 | +0.40 | +0.35 |

- Neither gate fixes h720. Both remove overlay benefit (transport/econ_fin). The h720 loss is not caused by overlays on seasonal records or by long half-lives.
- `ovs` stays in the code, off by default.

### The bar we must clear
- The level bar decays linearly from 1% (fresh king) to 0.5% over margin_warmup_blocks = 28,800 (about 4 days). It is judged on the challenger's LCB.
- Reign 13 started 11-04 04:33 UTC, so about 0.9% now and about 0.6% around 11-07.
- ovltrunk (+0.60% in the screen) is close but not enough yet.

### Next (arms_k13f)
- Trunk-phase dose 0.25 and 0.40, both seeds.
- Rationale: with the cooldown kept clean, the trunk may tolerate more overlay than all-phase did.

## Update 11-05 03:55 UTC: trunk dose (arms_k13f)
| arm | s0 | s1 | mean |
|---|---|---|---|
| ovltrunk (0.15) | +0.72 | +0.48 | +0.60 |
| ovlt25 (0.25) | +0.52 | +0.65 | +0.59 |
| ovlt40 (0.40) | -0.07 | -0.23 | -0.15 |

- **Dose curve:** a plateau at 0.15-0.25, then a collapse at 0.40.
- **By domain:**
  - Transport rises with dose: +1.7 / +2.4 / +2.2 (s0).
  - Health / energy fall: health +0.15 / -0.47 / -1.80, energy -0.35 / -0.48 / -0.80.
- **Reading:** one uniform rate trades transport gains against health / energy losses.
- **Next:**
  - Queued arms_k13g: level-only vs amplitude-only at 0.2, to see which overlay carries the gain and which the damage.
  - Feature `ovf` (per-family rate multipliers); arms_k13h ovft25 = trunk 0.25 with health / energy families muted, including the novel-stream epi_season_decay (~5% of records).
  - Stream composition (seed 0, 951 records): held_rate 56%, epi_season_decay 5%, conditional_stability 5%, road_commute_counts 2%.

## Bench gate: ovltrunk vs base (k13, 2026-11-05)

4 suites on cuda, ckpts from grid_k13 seed 0. FEV scores 65/100 tasks (multivariate skipped), so the strict gate says "partial"; diagnostic gate treats the 65 as the suite (same method as the old jsz05dr60 check, which failed at 0.459).

| Suite | n | ratio | LCB | win rate |
|---|---|---|---|---|
| GIFT | 97 | 0.9969 | 0.9937 | 0.577 |
| BOOM | 7371 | 0.9925 | 0.9896 | 0.572 |
| TIME | 98 | 0.9932 | 0.9897 | 0.786 |
| FEV | 65 | 0.9973 | 0.9945 | 0.585 |

**Passes: win rate 0.630 ≥ 0.5**, avg ratio 0.995 (better on every suite). Unlike jsz05dr60, the overlay gain is broad. Files: ledger/benchgate4diag_k13_ovltrunk_vs_base.json, ledger/benchgate4_k13_ovltrunk_vs_base.json.

## Verify: c1 = ovltrunk + qnt 0.5 (grid_k13, seed 0, 2026-11-05)
Paired windows (tools: .claude-work/tmp/pair_arms.py), same 6 files:

| Comparison | mean of files | per file | h64 / h256 / h720 |
|---|---|---|---|
| ovltrunk vs base | +0.78% | +0.49 +0.88 +0.67 +0.92 +1.08 +0.62 | +0.96 / +1.33 / +0.04 |
| c1 vs base | +0.56% | +0.20 +0.44 +0.57 +0.63 +0.88 +0.63 | +0.87 / +1.03 / -0.22 |
| **c1 vs ovltrunk** | **-0.22%** | -0.29 -0.44 -0.11 -0.29 -0.20 +0.01 | -0.09 / -0.31 / -0.26 |

**qnt rejected:** it degrades on 5/6 files and at every horizon (losses in econ_fin, nature, sales). This matches the 8-seed ledger figure of q50 (+0.06%, t 0.85), not the earlier 5-seed +0.15%. qnt stays in the code, off.
c2 (c1 + jmp) was killed before training; replaced by **j1 = ovltrunk + jmp 1.0** (arms_j1.json).

## Verify: j1 = ovltrunk + jmp 1.0 (grid_k13, seed 0, 2026-11-05)

| Comparison | mean of files | per file | h64 / h256 / h720 |
|---|---|---|---|
| j1 vs base | +0.66% | +0.74 +1.18 +0.23 +0.77 +0.70 +0.31 | +1.43 / +0.58 / -0.04 |
| **j1 vs ovltrunk** | **-0.12%** | +0.25 +0.31 -0.45 -0.15 -0.38 -0.31 | +0.48 / -0.76 / -0.08 |

Domains vs ovltrunk: transport +1.50, nature +0.41, sales +0.28; healthcare -1.84, web -0.65, energy -0.48, econ_fin -0.42.
**jmp rejected:** the same h64-for-h256 trade as on the old base, net negative. It stays in the code, off.
Next (queued 08:54): ovft25 (arms_k13h): trunk overlays 0.25 with the 12 health/energy families muted. This is a reasoned single update from the measured pattern: overlays help transport/econ_fin with dose but hurt health/energy.

## Verify: ovft25 (grid_k13, seed 0, 2026-11-05) - ACCEPTED, new candidate
Trunk overlays 0.25 / 0.25, 12 health/energy families muted (arms_k13h).

| Comparison | mean of files | per file | h64 / h256 / h720 |
|---|---|---|---|
| ovft25 vs base | **+0.98%** | +0.72 +1.28 +0.84 +0.74 +1.21 +1.08 | +1.43 / +1.49 / +0.01 |
| ovft25 vs ovltrunk | **+0.20%** | +0.23 +0.40 +0.16 -0.18 +0.14 +0.46 | +0.47 / +0.16 / -0.03 |

Domains vs base: transport +2.63, econ_fin +1.73, sales +1.20, nature +0.78, web +0.13, healthcare 0.00, energy -0.26. Muting removed the health loss and kept the dose gains.
Candidate = king + lcpr + ovl(0.25/0.25, trunk, family_rate_mult health/energy 0). Bench gate on its ckpt is running (bench_ovft25.sh).
