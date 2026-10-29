# Current generator: weaknesses, and what the initial update changed

The code under analysis is `generator/generator.py`: king `04e226724e3b` after the first refactor step. The analysis date is 2026-10-29.
Measurements were taken on WSL Ubuntu with Python 3.11 and the pinned subnet packages, using one pinned core, BLAS threads = 1, RLIMIT_AS 2048 MB and no network.
Tools: `tests/perf/run.sh` (throughput/memory), `tests/v2/validate.py` (cascade `SeriesValidator` under the v2 policy) and `tests/golden/run.sh` (byte-identical regression).

## 1. Measured weaknesses (before the update)

| # | Weakness | Evidence | Severity |
|---|---|---|---|
| W1 | **Not v2-valid:** yields `(4096,)` and `(2–5, 4096)`; v2 requires exactly `(32, L)` every yield | 120 s run: 15,888 × 1-ch, 5,108 × 2-ch, 2,236 × 3-ch, 287 × 4-ch, 4,615 × 5-ch | Fatal (rejection burns the hotkey) |
| W2 | **The best late-stream layers never fire under v2:** C91/C124B2 hold extension and YQH open at 2.66e9 points; C215-LP (the 10-22 king's main gain) at 5.33e9; a v2 child emits only 1.5625e9 | Budget constants `_C91_CHILD_BUDGET` / `_YZ_CHILD_BUDGET` = 13.32e9, `_C215LP_STREAM_POINTS` = 13.32e9 (pre-v2 child) | High (silently loses the latest kings' strengths) |
| W3 | **Near-duplicate channels:** once rows are packed, independent step series can be ~identical (|corr| = 1.0) | Seed 0: 2 of 300 records ≥ 0.999 (cross-row) | High if `channel_corr_mode` is ever set to `enforce` (shadow today) |
| W4 | **Memory margin:** VmPeak 1,593 MB against the 2,048 MB cap, with 3 hard-coded family-worker threads on a 1-core child | `perf/run.sh` | Medium |
| W5 | **Slow start:** about 25 s to the first yield (113 numba kernels with `cache=False`, compiled every start) | `cascade verify --quick` fails `runtime_timeout` (30 s budget); `score`/`iterate` run the quick check | Medium (tooling only; full verify/submit/production allow 5,400 s) |
| W6 | **float64 output** where shards store float32; no final finite/float32-range guard | dtype `<f8` | Low/medium (any inf or > 3.4e38 value = generator fault) |
| W7 | **Corpus mix tuned for the pre-v2 warm-start lineage:** about 64% `held_rate`, about 80% hold-like | `config.json` engine weights | Unknown, likely material in the v2 **random-init** window; needs GPU experiments |
| W8 | **Accretion:** about 35 nested layers, many dead or zero-rate paths, seasonal calibrations (PAUT autumn prices) that will drift | `notes/KINGS.md` | Maintainability; being addressed by the atomic refactor |

Throughput is **not** a weakness: about 1.95M values/s per core, 6.7× the v2 requirement (289k/s).

## 2. Initial update (this commit)

| Change | Fixes | Strength it brings in |
|---|---|---|
| New outermost **v2 pack layer**: parent rows are packed in stream order into `{"values": (32, 4096) float32, "groups": int64[32]}`. Each parent row is its own group (canonical labels); bounded lookahead of 64; rows that don't fit wait for the next record; a row is split only if nothing fits | W1, W6 | Keeps the coupled multichannel rows of kings 16–17 (k price/volume pair, partner/teach channels) together as one attention group, while unrelated rows never attend to each other |
| **Near-duplicate guard** in the packer: a row is skipped if it would put any two channels of a record above \|corr\| 0.998, using the trainer's own formula (`channel_stats._corr_matrix`, std floor 1e-12) | W3 | Generalises ACUH's (10-13 king) 0.999 channel guard to the whole record |
| **Budgets rescaled to the v2 child:** `_C91_CHILD_BUDGET`, `_YZ_CHILD_BUDGET`, `_C215LP_STREAM_POINTS` = 1.5625e9 (50e9 / 32 children) | W2 | Re-enables the c124-b2 quiet-regime hold extension, YQH station holds and C215-LP tail continuation at the same *relative* stream positions they were designed for |
| `_PRODUCER_WORKERS = 1` | W4 | — (output unchanged: family groups are order-independent) |
| Finite + float32-range guard (`nan`→0, clip to ±1e30) before the float32 cast | W6 | — |

### Results after the update
- `tests/v2/validate.py`, 4 seeds × 300 records, including 63-bit seeds:
  - every record passes cascade's `SeriesValidator` (32 channels, length, finite, float32-safe, `groups` canonical);
  - deterministic; duplicate fraction 0.0; mean 15.9 groups per record; max |corr| 0.9978 (< 0.998).
- `tests/perf/run.sh`: **1.85M values/s (6.4× the v2 requirement)**, VmPeak **1,410 MB** (was 1,593), first yield 24.9 s.
- `tests/golden`: the inner king stream (`_V2PackParent`) is **byte-identical** to the baseline in both modes. New v2 goldens were recorded (`expected_v2_*.json`).
- `cascade verify --quick` still times out (W5). `--live` reports `live_status_unavailable` because the v2 era init is not published yet, which is expected before launch.

## 3. Open items, ranked (not done: they need GPU experiments or the live contract)

1. **Live verification after launch:** `cascade verify generator --live --json` (full). The offline intersection policy rejects `groups`, so the offline full verify is expected to fail on `groups` until the v2 contract is live.
2. **Corpus mix for random init (W7).** Candidate experiments on Cascade MoE 17.58M / 69.02M with real held-out pools:
   - (a) the current mix;
   - (b) hold-like share reduced to about 50%, adding broad dynamics (strength of kings 01–05) and the TempoPFN-style priors (KernelSynth/GP, unused since king 01);
   - (c) more daily-cadence and long-horizon (h=720) content.
3. **Group policy:** per-row groups (now) vs. singletons only vs. one joint group. Measure on the eval-pool's multivariate windows and on the univariate majority.
4. **Startup time (W5):** find which kernels dominate compile time; consider compiling lazily only what the config uses.
5. **Seasonal drift:** PAUT (autumn day-ahead prices) and other date-specific calibrations should be re-checked against fresh pool snapshots.
6. **Dedup:** the v2 output differs from every king (none is v2-valid), but the final submission should still carry our own improvements, not just the packer.
