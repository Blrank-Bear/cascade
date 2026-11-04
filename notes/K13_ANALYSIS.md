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
