# Local test pool, GPU test plan and submission timeline

## 1. What the "problems" are, and when they are known (checked in `upstream/docs/EVAL_POOL.md`, `publish-pool.yml`)

- **The test set is not published in advance.** A new private snapshot is built daily at 03:00 UTC from public live feeds. It is activated at a *future* epoch boundary and pinned in the trainer-signed manifest.
- The exact **windows** are a seeded draw from the settlement's epoch-boundary **block hash**, which is unpredictable before that block.
- Snapshots are revealed on HF (`Tensor-Link/cascade-eval-pool`) only **after** a newer snapshot supersedes them (about 48 h; the latest public one on 2026-10-29 is 2026-10-25). By design, a revealed pool can never be selected by a current or future round.
- What *is* knowable: the **distribution**. It comes from the same feeds and is refreshed daily, so the 2–4-day-old snapshots are a close proxy for the next settlement's pool.
  - The 10-23..10-25 snapshots each have about 3,300–3,450 series, a median length of about 1,500 points (25% under 900), about 9% multichannel.
  - Cadence mix: H 24%, D 20%, 15min 18%, min 14%, 5min 13%.
  - Domains: web_cloudops/econ_fin/nature about 17% each, transport 14%, energy 12–14%, healthcare 11%, sales 10%.

### Local test pool policy
1. Before every comparison, refresh: `tools/pool/fetch_snapshots.py --out .claude-work/data/pools --latest 3 --stats`.
2. Score on **each of the 3 newest snapshots**, with 2 round seeds each (`--round-seed`). A candidate must win on all of them, not on average.
3. Use the v2 verdict ladder (horizons 64/256/720, 4,000 windows) via `tools/duel/duel.py score`, not the single-horizon `cascade score` default.

## 2. GPU test plan (once GPUs are rented)

Rented box: Linux, CUDA, an 80 GB H100-class GPU for the 1.23B model; any 24 GB+ GPU for the 17.58M/69.02M models.

| Stage | Model | Budget | What it decides | Runs |
|---|---|---|---|---|
| A. Smoke | 17.58M | `--hours 0.05` | Pipeline works on GPU; measure steps/s | 1 |
| B. Screening | 17.58M or 69.02M | `--hours 0.5–1` | Mix rate (`v2_mix.json` rate 0 / 0.15 / 0.3), group policy | 3–6 configs × 2 seeds |
| C. Throughput | 1.23B | 200 steps | Does 23,841 steps fit in 5 h? (needs ≥ 1.33 steps/s) | 1 |
| D. Confirmation | 1.23B (live contract) | full | Final candidate vs. baseline (rate 0) × 2 seeds; LCB must clear the margin with room to spare | 4 |
| E. Bench gate | 1.23B checkpoint | `benchmarks/` | GIFT-Eval/BOOM/TIME/FEV regression check | 1–2 |

Per pair: `duel.py train` both sides with the same seed and config → `duel.py score` on the same pool and round seed → `duel.py judge` (level units with margin 0.01 for the random-init window).

## 3. Submission timeline (proposal)

| When (UTC) | Event | Action |
|---|---|---|
| 10-30 09:00 | v2 entry window opens | — (do not submit untested) |
| 10-30 12:00 | v2 Lane A launch target | `cascade status --json`; `cascade verify generator --live --json` as soon as the contract is live |
| 10-30 → 11-01 | GPU stages A–D | — |
| **11-01 12:00 (target)** | **Submission deadline we set** | Submit only if stage D shows a clear win on all 3 snapshots × 2 seeds, plus a full `verify --live` pass |
| about 11-06 12:00 | End of the random-init window (14 eras of about 12 h) | After this, duels use warm starts and increment units, so every local result must be re-run with `--warm-start live` |

Why 11-01:
- It leaves about 5 days of the random-init window, where the bar is a level LCB of 1% against a fresh king and a level-unit win starts at 50% of Lane A.
- It leaves room for the queue: generation (90 min) + training (≤ 5 h) + settlements every about 3 h. None of these is guaranteed.
- Lane A allows **one lifetime submission per hotkey**, so missing the deadline is better than submitting an unproven entry.

## 4. Stage-B grid runner (added 2026-10-29)
On the GPU box, after `tools/pool/fetch_snapshots.py --latest 3`:

```
cd upstream
python ../tools/duel/grid.py ../tools/duel/arms_stage_b.json --chain-toml CFG \
    --work ../.claude-work/grid_b --hours 0.5 --device cuda --pools 3 --round-seeds grid-0,grid-1
```

- **Arms:** base, hist55, pool2_25, mix30, singleton and pool2_hist. The switch files are described in `notes/V2_EVAL_FACTS.md`.
- **Process:** each arm is trained once with the same seed and budget, scored on 3 snapshots × 2 round seeds, and judged against base.
- **Output:** `summary.json` lists wins per arm, out of 6.
- **Resuming:** every step is cached, so a killed run resumes where it stopped.
- **Smoke test:** the CPU version is `tools/duel/grid_smoke.sh`. It ran OK end to end on 2026-10-29. With a 0.0002 h budget there is no signal, and the LCB is NaN at 60 windows.
- **Promotion rule:** an arm goes to stage D only if it wins at least 5 of 6 cells at the 0.5 h budget, with the same sign at every horizon.
