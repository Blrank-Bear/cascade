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

---

# Strengths and weaknesses of all kings (reigns 01–17 plus the October kings)

Reign length = rounds held (`champions/archive/README.md` on `main`). It is the best available proxy for how hard a king was to beat.
The provenance files carry no scores or margins. The October kings a3e342, f33f40 and b20b875 are not in the archive table.
Archive entries with 0 rounds have no recorded first round, so their reign length is unknown.
The current king 04e22672 is archive entry `13-5Gsa19SFpRY9` (uid 31): first round 2026-10-23 and **25 rounds**, still reigning at the 27 Oct sync.
The assessments below are my judgment from reading the code, not measured results.

## Per king

| # | King | Rounds | Strengths | Weaknesses |
|---|---|---|---|---|
| 01 | fullctx-spectral-v12 | 7 | Clean, vectorised numpy, 14 broad dynamics families (AR, regime, OU-vol, spectral GP, chaotic); fast and simple | Generic: no calendars, cadence or measurement artefacts; fixed L=4096; dropped the TempoPFN priors entirely |
| 02 | heat15 | 4 | Adds sensors, conditional stability, calendar counts, observation/augment layer, seasonal-period table | Curriculum adds complexity for little gain; still mostly generic |
| 03 | gen-76e2 | 4 | Real-world shapes: tides, weekly demand, flow recession, rate staircases | A small fork; short reign, so the increment was narrow |
| 04 | foreverking | 14 | First big bet on step_level / piecewise-constant holds (50% exact flats), which beat generic dynamics | Obfuscated names (k00..k20); narrows the corpus toward flats |
| 05 | gen33 | 6 | Variable length 64–4096, numba AR kernels (speed) | Even more weight on holds (k14 .39, k15 .27); variable length wastes budget |
| 06 | cs35step25 | 20 | Decisive shift: conditional_stability .41 + step .29 + ar2; simple and strong | Nearly three families only, so it has diversity holes |
| 07 | gen334 | 8 | 33 families; split cs into drift/flat/countwalk/pulse; energy and healthcare reporting cadence | Diluted the winning cs mix; short reign |
| 08 | garuda | 21 | 37 families, good balance | Obfuscated (`_qsvNN`); hard to audit |
| 09 | jenn11 | 31 | 40 families plus tsmixup, pad_prefix, tail_rebase (the first tail law) | 160 KB; complexity starts to balloon |
| 10 | cascade-apex | 36 | 58 families: met/ops/epi/hawkes/garch/lorenz "chronoforge" zoo; very diverse | Embedded **exec'd source** (scan high=2); it would be refused today |
| 11 | p1-top-health | 44 | held_rate .364 dominant plus 75 families; heavy-traffic counts, cycle profiles, SARIMA | exec'd code; heavy concentration on one family |
| 12 | vant-energy-lock85 | 12 | Energy load/price/solar, admin counts, latency queues | Narrow energy focus; short reign |
| 13 | gen-64a0 | 23 | Cumulative counters, econ staircases, settle_hold, renewal persistence | exec'd code; 480 KB |
| 14 | V444 | **57** (longest) | Validated long-cycle (257–512 lag) predictor: a tiny, well-targeted change; the strongest increment in the lineage | exec'd code; weights otherwise unchanged |
| 15 | gen (594 KB) | 21 | 91 families; sticky stations, epidemic season decay, end-of-feed fade | exec'd code; accretion, with many near-zero families |
| 16 | 5HDv "p2" | 18 | First 2-channel rows in a wrapper that keeps the parent byte-identical | Packed/exec'd sources; channels unrelated to each other |
| 17 | 5DZv champion-anchored-pack | 9 | Channel 1 rides free under series_points billing | Exploits a billing rule that v2 removes; exec'd code |
| 17 | 5D7L w9qedrki | – | De-packed, no exec; "teach" stream fitted to real pool feeds (CDC NSSP, RKI, IXP, web) | Fits named feeds, so it drifts as the pool rotates |
| 17 | 5Epw | – | "Weakness" channels: energy, civic, AQ, FX/yield/crypto | More stacking with rare coins; hard to control the mix |
| 16 | 5ETn | – | k micro-price/volume pair (the only real coupling) | 981 KB; up to 4 loosely coupled channels |
| 16 | 5GMz c159 (bc25aa43) | – | Clean single module (no exec); quiet-tail gate; p25 daily/weekly stage | ~21k lines; held_rate .466 |
| – | c128-wsT2 (a3e342) | – | Evidence-based quiet-regime hold extension; weakness channels chosen where the model lost to its init | Fragile late-stream budget gates |
| – | c246-acuh (f33f40) | – | Calibration fix (forecasts too low/narrow) with a correlation guard against duplicate channels | Comments stripped, so much harder to audit; tiny insert rates |
| – | c1933 (b20b875) | – | Broadest pool-native texture, short padded histories, yearly seasonality, perf work | held_rate doubled to ~64% of engine rows; much dead code |
| **13** | **04e22672 (current)** | **25+** | Scorer-aligned tail laws (hold / median cycle / line over the last 256–720 points); bit-exact speedups; AQ/sensor recalibration | ~35 nested layers; seasonal tuning will drift; pre-v2 budget gates; float64 and threads, a risk under 2 GB |

## What consistently worked
1. **Holds, steps and staircases:** every long reign from 06 on leaned into them.
2. **Tail laws aligned to the scorer:** tail_rebase (09) → validated long cycle (14, the longest reign) → LP/MLPX (current). This was the single most effective idea.
3. **Real-data realism:** measurement artefacts, sentinel codes, integer and zero-inflated counts, reporting cadence, calendars, cadence-correct periods.
4. **Error-driven additions:** families added exactly where the trained model lost to its init on real sources.
5. **Paired-duel engineering:** forking the parent byte-identically plus one seeded layer isolates the gain.

## What consistently hurt or limits them
1. **Over-concentration:** about 64–80% hold-like content. That is risky for the v2 random-init window, where the model must also learn smooth seasonality, trends and noise from scratch.
2. **Accretion:** 14 → 91+ families and 35 layers, many dead; obfuscation and stripped comments.
3. **No real multivariate structure:** extra channels are mostly unrelated rows stacked to exploit billing.
4. **Fitting to the pool snapshot:** families tuned to named feeds and seasons decay as the pool rotates.
5. **Rule-dependence:** v1 billing tricks, budget gates, exec-packed code and 1–5-channel outputs all break under v2.
6. **Fixed L=4096 everywhere:** they never explored longer series cropped into several windows.

## What this means for our v2 entry
- **Keep:** holds (at a moderate share), tail laws, measurement realism, cadence and calendar correctness, short padded histories, seeded substreams.
- **Fix:** a balanced mix for training from random init; genuine coupled groups in the 32 channels; a clean single module; v2-sized throughput and memory.
- **Avoid:** copying king code, exec/packed code, budget-gated tricks, over-fitting to the current snapshot.

## Reign 13 king (first v2 king): 716765dc, uid 220, crowned 2026-11-04 04:33 UTC
- Study copy: `reference/kings/2026-11-04-716765dcf2f6/` (static read only, never run).
- Base: c268 (a later v1 lineage than our c251-based foundation), byte-identical above its K0 banner.
- Layers appended on top (none adds new series families):
  1. **K0 serial mode + budget rescale**: budget-gated layers open at the same stream fraction as in v1.
  2. **K0-32G packer**: exactly 32 channels, one group label per packed record.
  3. **MAGGUARD**: rows with peak > 1e4 rescaled (energy-score float32 overflow).
  4. **SINGLETONS**: every channel its own group (np.arange(32)); about 88% of eval windows are univariate.
  5. **MVKEEP**: 10% of multichannel records keep their group, so variate attention still trains.
  6. **PADK-NEAR**: channels whose first move is in the last 1024 points become exactly constant
     (teaches the "long constant prefix" forecast case).
  7. **LCP-LATE**: from child yield 10,837 on, the start of the WSD cooldown at update 21,674 of
     23,840, several hooks switch to "late" values. It is a curriculum keyed to the trainer's schedule.
- **Why our screen could not see most of this:**
  - The 28m / 396-step screen consumes about 6.4k yields in total, against about 11.9k per child and
    23,840 updates in a real round.
  - Stream-position effects never occur in the screen: budget-gated layers opening at 20% of a child
    stream, and the cooldown switch.
  - Singleton groups were tested only once, combined with jumps (jsz05sing), on one seed
    (-0.98%), and dropped. That is a single-seed, multi-feature verdict, the same noise trap as
    mrovlg60.
