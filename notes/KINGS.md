# Subnet 91 kings: analysis of the last five Lane A kings

These notes cover the snapshots in `reference/kings/`. I studied them by reading and diffing; none of the code was run.
Line numbers refer to each snapshot's `generator.py`. For the earlier lineage (reigns 01–17), see `notes/ANALYSIS.md` §6.

## Lineage at a glance

| Synced | Digest | Name | Change vs. previous king | Lines |
|---|---|---|---|---|
| 10-06 | bc25aa43 | c159 | baseline: engine plus 8 channel-stacking wrapper stages | 21,384 |
| 10-10 | a3e342a1 | c128-wsT2 | **append-only** +1.8k: hold-extension layers plus a 3rd "weakness" channel | 23,153 |
| 10-13 | f33f40a4 | c246-acuh | comments stripped (−4.2k); +1.4k: univariate inserts plus a 4th channel | 21,080 |
| 10-18 | b20b875b | c1933 | +7.5k "Y" families, held_rate ×2, yearly seasonality, a 5th channel, station holds | 28,308 |
| **10-22** | **04e22672** | (era 2594) | +3.2k: numba speedups, tail-continuation laws, AQ/sensor inserts, autumn price drift | 31,482 |

**The pattern:** every new king **forks the previous king byte-for-byte and stacks one new wrapper class on top**.
Each new layer uses its own seed tag, so the parent's rows stay identical and the paired duel isolates the increment.
The current king is about 35 nested `class Generator(_Parent)` layers.

## Step by step

### c159 → c128-wsT2 (10-10)
- **c91 hold layer (21387):** late in each stream (past 3/5 of the budget), exact runs of ≥32 identical values are lengthened by 64 + Geom(1/96) points. The start is cropped to keep L=4096.
  - The aim is sharp quantiles on windows that end in a hold.
- **c124-b2 quiet gate (21490):** a hold is extended only if ≥95% of the 256 prior differences are exact repeats.
  - The comment's real-pool evidence: runs continue 29–47% of the time after quiet regimes but only 9–19% after active ones.
- **c128 weakness channel (21566):** a 3rd channel on 2-channel rows, drawn from tidal .38 (1-min IOC tide gauges with real M2/S2/K1/O1… constituents), hydro .33 (USGS/EA water temperature, stage, flow, SNOTEL, -999999 sentinels), infra .15 (IXP 5-min, Wikimedia 1-min with a 1440 period, Prometheus scrapes) and mobility .13 (MTA, bike counters, car parks, docks).
  - These were chosen where **the trained king was worse than its init** on real sources.
- **Likely gain:** nature, web_cloudops and transport, plus full-amplitude daily cycles at h256/h720.

### c128 → c246-acuh (10-13)
- About 4.2k lines of comments and docstrings were removed. AST diffing shows the logic is unchanged apart from one inserted block.
- **XZ inserts (19514):** extra standalone 4096-point rows: air quality .01, 1-min/1440-period rates and tides .01, and small integer trade/edit counts .01.
- **ACUH 4th channel (20753):** air quality .50 (episodes breaking above the past range), USDA daily prices .20, CDC/RKI health .15, CO2 intensity .15. Channels with |corr| ≥ 0.999 against existing ones are rejected.
  - Its stated motivation: the king's forecasts were **too low and too narrow** on real duel windows.
- **Likely gain:** WQL calibration (upper quantiles) for econ_fin, healthcare, nature and energy at long horizons.

### c246 → c1933 (10-18)
- **Config changes:** `held_rate` doubled (normalised: about 64% of engine rows), a new `year` seasonality (coarse .5), and RKI epidemic weight cut from .18 to .068.
- **About 6.6k lines of "Y" families (21671–27370).** Each builds a real-like **short history left-padded with its first value**, mimicking how short eval series are padded:
  - 15-min grid (co2/solar/wind/price/load) and 1-min tidal
  - interest rates, counts, stale/frozen stations, ARI/COVID/flu/RSV waves, civic counts, hydro
  - bike docks, station fuel prices, token/FX micro-prices, ozone/PM with 999.9 codes
  - hourly Poisson-gamma counts, transport, sales, econ, and 5–60-min energy cells
- **New stages:**
  - YZ inserts.
  - YC appends one more channel to about 94% of eligible moving rows, so rows reach up to 5 channels.
  - YQH stretches holds in integer "station" channels (power-law 96–3072).
  - The hold layers now open at 1/5 of the budget instead of 3/5.
  - K2 is switched off.
- **Perf:** `_FastCoin` replaces per-row SeedSequence calls, numba stats, and a run-ahead producer thread.
- **Likely gain:** pool-native texture for energy, econ_fin, transport, web and nature; sharper held tails, so lower MASE at h64/h256; and the yearly term helps at h720.

### c1933 → 04e22672 (10-22, current)
- **c251 P1–P13:** bit-exact numba rewrites of hot paths, for speed only.
  - The `# cascade era 2594 entry` header shifts every line by one, which quietly disables old `co_firstlineno`-gated patches. The output is unchanged.
- **c259 bundle (30975):** AQR hourly NO2/PM recalibrated on 351 luchtmeetnet/irceline series, and OSM openSenseMap PM2.5 at a 150-s cadence. Each is .004 of rows, behind a hygiene gate.
- **c215-LP continuation law (31040):** on the last 60% of the stream, a boundary is picked 256–720 points before the end. Channels that end in an exact hold get their held value continued to the end.
- **c233-MLPX (31175):** if the pre-boundary window passes the king's own law tests, the tail is replaced with a **median-cycle template** (lags 7/12/24/48/96 or a validated long cycle with ACF ≥ .5) or a clipped line.
- **c261 PAUT (31420):** an autumn drift in 15-min day-ahead prices (energy_charts): troughs deepen and levels rise 13–17%.
- **SALT:** the seed is mixed with a salt, which redraws the whole corpus.
- **Likely gain:** it teaches the forecaster the scorer-side continuation laws (hold / seasonal-naive / line) on channels the engine never touched. That should lower MASE and WQL broadly at h256/h720.

## Current king architecture (04e22672)

```
SALT(seed→63-bit) → RA(run-ahead) → MLPX → LP → C259 inserts → … YQH, YC, YZ → ACUH → XZ → C128 → C124B2/C91 holds
  → S2, S1, K, P25, W86B, BAND → w9qedrki: engine(g0) + partner + teach (Q=.25 → 2nd channel)
     → _EngineGenerator: _BaseGenerator (85%) + "novel" families stream (14.78%)
        → _BaseGenerator: chunked batch builders (n,4096) → measurement artifacts → integer prior
          → tail_rebase (hold/periodic/linear tail over the last 256–720 points) → tsmixup .18 / pad_prefix .05
```

- **Engine mix (normalised):** held_rate 63.6%, conditional_stability 7.5%, step_level 2.3%, sticky_station 2.0%, econ staircase 1.7%, and so on. About **80% is hold-like**.
  - The rest covers weather/hydro, transport/web, energy/price, counts/admin, epidemiology and generic AR/GARCH/GP families (each under 0.5%).
- **Families fitted to named eval feeds:** energy_charts day-ahead prices, luchtmeetnet/irceline AQ, openSenseMap PM, RKI, IXP, tide gauges, bike docks and AEMO.
- **Seeding:** 63-bit safe. It uses `default_rng` plus per-layer `SeedSequence([seed, TAG], spawn_key=(i,))`, and a hand-written vectorised SeedSequence-to-PCG64 replica that self-tests at import.
  - The partner stream's seed space is only 31 bits.
- **Output:** float64, always L=4096, shape `(4096,)` or `(C≤5, 4096)`. It never emits `groups`.
- **Perf:** batched numpy, 113 numba kernels (`cache=False`, so they recompile on every start), and producer/run-ahead/3 worker threads, which are useless on a single core.
  - It was sized for a pre-v2 child budget of 13.32e9 points.

## Why it can't be resubmitted for v2, and what that means

1. **Channels:** v2 requires exactly 32 channels on every yield. The king yields 1–5 channels.
2. **Budget-gated layers never fire:** C91, YQH and LP are keyed to a 13.32e9-point child. v2 children produce about 1.56e9 points, and points are billed differently.
3. **Memory risk under 2 GB of virtual address space:** (2048×4096) float64 temporaries, queues, several threads with glibc arenas, and LLVM/numba.
4. **Hygiene:** `threadpoolctl` is imported without being pinned, there are hard-coded asserts, state is kept across `generate()` calls, and module globals are mutated.
5. **Dedup:** forking it, as every king has done so far, would be dropped as a near-copy unless the v2 output really differs. The safe approach is a clean v2 design that reuses *ideas*, not code.

## Takeaways for our v2 generator

The proven ideas (worth re-implementing cleanly):
- **Tail continuation laws** for the last 256–720 points: hold, seasonal-naive with a validated cycle, or a line. They line up exactly with the scoring horizons and with MASE's seasonal-naive denominator.
- **Quiet-regime hold extension:** sharp quantiles when a series really is held.
- **Measurement and observation realism:** censoring, quantisation, stale holds, sentinel codes, integer and zero-inflated priors, reporting cadence.
- **Short histories left-padded with the first value,** matching how short eval series are presented.
- **Cadence- and calendar-correct seasonality:** 1-min/1440, 5-min/288, 15-min/96, hourly 24/168, daily 7, plus yearly.
- **Error-driven additions:** find real sources where a trained model beats its init the least, and add a family for them.
- **Per-record substreams** (seed, tag, i), so components compose deterministically.

The gaps we could exploit:
- **Use the 32 channels properly:** pack independent univariate series as singleton `groups`, plus a few **genuinely coupled** groups (price/volume, load/price/renewables, station networks, hierarchical sums).
  - No king has ever trained real multivariate structure.
- **Less hold-heavy and broader:** the king is about 64% `held_rate`. In the v2 random-init window the model starts from scratch, so the corpus has to teach basic seasonal, trend and noise structure too.
- **More daily-cadence content and long horizons (h=720):** this is thin outside the partner families.
- **Length:** L=4096 fits the budget best. Longer series up to 32768 are cropped into 4096 windows, giving more varied context per seed.
- **Throughput and memory by design:** single-threaded, float32 where safe, small batches, under 2 GB of virtual memory, and above 290k values/s per core.
