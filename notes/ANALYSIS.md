# Subnet 91 (Cascade): analysis for mining Lane A in v2

Source: `upstream/` = TensorLink-AI/cascade, branch `cascade-v2` @ b3a479b (2026-10-28).
Paths below are relative to `upstream/`. The values are the checked-in mainnet config.
Always re-check them against `cascade status --json` before acting.

## 1. What a miner does

You submit a **deterministic Python data generator**. It is code only: no weights and no bundled data.
The operator generates a corpus from it on CPU, trains a fixed forecaster from scratch or from the era init on **only that corpus**,
and scores the result against the king on a private pool of recent real series.

- **Model:** Cascade MoE Base 1.23B (112M active), 21-quantile head, 10 blocks, 32-point patches, context 4096 (`docs/MODEL.md`).
- **Training:** 23,841 updates × 512 channel-rows × 4096 points ≈ 50B points, with a 5 h GPU wall (18,000 s). The scored checkpoint is the end of the linear cooldown (the last ~2,167 steps).
- **Costs:** the miner pays for their own GPU leg through Lium, Shadeform, Vast or Runpod (`docs/MINER.md:127`, `:550`).
- **One lifetime Lane A submission per hotkey** (`docs/MINER.md:336`). A miner-caused rejection spends it. That includes a generator fault, non-finite loss, packed code or a duplicate.

## 2. Timeline

| When (UTC) | Event |
|---|---|
| 30 Oct 09:00 | v2 entry window opens; a fresh reveal is required |
| 30 Oct 12:00 | v2 Lane A target; it starts at the first era boundary after this |
| ~first 14 eras (~7 days) | **Random-init window**: no warm start, duels judged in *level* units |
| afterwards | Warm start from the king's pre-cooldown weights; duels judged in *increment* units |

Settlements are 900 blocks apart (~3 h), with 4 per era (~12 h).

## 3. Generator contract (rejection = spent hotkey)

- **Layout:** `generator.py`, `config.json` (a JSON object) and `requirements.txt`. Only `*.py *.json *.txt *.md` survive upload. Repo size is capped at 128 MB.
- **Class:** `generator.Generator(DataGenerator)`, constructed as `Generator(config_dir, *, seed)`. It needs a `name` property and `generate(n_series)`, which yields lazily.
  - `n_series` is an upper bound (~24M in production). Never preallocate from it, and never yield more than it.
- **Each yield** is a float ndarray `(32, L)`, **exactly 32 channels**, all finite and within float32 range.
  - L must be ≥ 64. The offline check caps it at 4096; the live v2 shard tier allows up to 32768. Verify with `--live`.
  - Records `{"values": arr, "groups": int[32]}` are allowed. `groups` must use canonical first-appearance labels 0..k. **Any other key is rejected.**
  - Offline verify (no `--live`) rejects `groups`, so test groups only with `--live`.
- **Determinism:** the output must be a byte-identical function of the seed. Seeds are **63-bit** in production but 0 in verify.
  - Use `np.random.default_rng(seed)`. `np.random.seed` / `RandomState` crash on seeds ≥ 2^32, which only shows up live.
- **Imports:** allowlist is numpy, scipy, pandas, statsmodels, numba, torch, scikit-learn, gpytorch and networkx, at most 16 packages, in `pkg==ver --hash=sha256:...` lines.
  - The runtime is the pinned `[generation]` extra (numpy 2.4.6, scipy 1.17.1, torch 2.4.1, …).
  - Blocked: socket, urllib/requests/http*, subprocess, ctypes, cffi, pickle, marshal, shelve, multiprocessing and `cascade.trainer` / `cascade.validator` / `cascade.shared.chain`.
- **No code in strings:** strings of 200+ characters that decode to Python are scanned. The testnet config uses `reject`, so test against it to be safe.
- **Sandbox (per CPU child):**
  - 1 core with BLAS threads = 1, **2048 MB virtual memory** (importing torch is risky)
  - 90 min wall, 10,800 s CPU, a 1,800 s stall limit between yields, no GPU and no network
  - Strict isolation needs Linux namespaces, so on Windows **use WSL2/Linux** for full verify.
- **Duplicates:** at most 5% exact duplicate series. Copies of the template or the king are dropped and still burn the hotkey.

## 4. Throughput: the hidden constraint

- The target is **50B points across 32 children in 90 minutes**. That is ≈ **290k values/s per core**, or ≈ 2.2 series of shape (32, 4096) per second per core.
- If the corpus falls short, training ends at `corpus_exhausted` **before the cooldown**, giving an un-annealed checkpoint that will almost certainly lose.
- Short series waste budget: each step takes 16 series of 32 channels, so with L=1024 the 23,841-step cap is hit at ~12.5B points.
- **Best fit: L = 4096**, or a multiple of it, since longer series are cropped into 4096-point windows.
- Generation speed is not scored directly, but it decides whether you get the full schedule.

## 5. How the duel is judged

- **Pool:** tsbench-forge, ~90 live public feeds across 7 domains (econ_fin, energy, healthcare, nature, sales, transport, web_cloudops).
  - Frequencies are **daily or faster only** (30S … H, 8H, D).
  - Refreshed daily. Targets are the **latest real observations**.
- **Windows:** one per series per horizon, at horizons **64 / 256 / 720**, ~4,000 windows in total.
  - Draws are balanced by domain and equalised by horizon.
  - Context is up to 4096 points, but often much shorter.
  - Most windows are univariate.
- **Metric:** `sqrt(geomean_windows(WQL) × geomean_windows(MASE))`.
  - WQL uses the 9 quantiles 0.1..0.9 taken from 100 sample paths.
  - MASE uses the sample median against seasonal-naive (H=24, D=7, 5min=288, 15min=96, minute=60).
  - The score is scale-invariant and every window counts equally. **Point accuracy (MASE) is half the score**, and the 0.01/0.99 tails earn nothing directly.
- **Duel:** paired, on the same windows. Bootstrap of B=10,000 over **source-family clusters** (one-sided α=0.05). One settlement win is enough.
  - *Random-init window:* LCB of (king−chal)/king must be ≥ **1%** against a fresh king, decaying to 0.5%.
  - *Warm start:* increment units relative to the init, with a margin starting at 0.10 and decaying to 0.01 over ~2.5 days.
  - There is one training seed, shared with the king, so seed noise is absorbed only by the margin.
- **Public benchmark veto** (runs only on a private-pool winner) across GIFT-Eval, BOOM, TIME and FEV. All three must hold:
  1. the suite-equal geomean ratio is < 1;
  2. no suite is significantly worse by more than 1%;
  3. the mean task win rate is ≥ 50%.
- **Rewards:** a level-unit (random-init) win starts at 50% of Lane A. Increment wins pay 25–80% depending on LCB. Each passed king check adds +10 points, up to 95%.
  - At launch a 95% burn applies until the first v2 king is crowned.

## 6. Champion lineage (`champions/`)

- There are 17 reigns, all **pre-v2**: Toto2, 1-D yields, with stacked 2–4 channel rows from reign 16 on. **None is v2-legal.**
- **Correction:** the `cascade-v2` branch's `champions/king` is stale (6 Oct, `bc25aa43…`). Per `main`'s 27 Oct sync, the current king is `04e22672…` (31k lines). There were 4 dethronements after 6 Oct, and all 5 snapshots are in `reference/kings/`, which are also pre-v2.
- The design described below is `bc25aa43…` = `16-5GMz…` ("c159"): 995 KB and ~21k lines.
  - Its engine has ~91 univariate families: held_rate .466, conditional_stability .110, step_level .034, sticky_station, gauge_rain, econ staircases, tides, energy and more.
  - It adds an observation layer (censoring, spikes, time warp, hold blocks, tsmixup).
  - On top of that is a chain of 8 wrapper stages adding partner channels (teach streams fitted to pool feeds, micro-price/volume pairs, civic/energy channels).
- **Trend:** generic AR/GP mixtures (01–05) gave way to held, flat and step-level regimes (06+), then heavy imitation of real-data quirks (calendars, reporting cadence, quantisation, counters), then explicit targeting of named pool feeds.
  - The original TempoPFN priors (KernelSynth, ForecastPFN, CauKer) were abandoned after reign 01.
- The past kings are worth studying as domain knowledge only. The v2 random-init window resets the lineage, and an exact or near copy is dropped by dedup.

## 7. Strategic takeaways

1. **The first v2 king is wide open.** The old king can't compete under the 32-channel rule, the random-init window needs only a ≥1% level LCB, and a win starts at 50% of Lane A.
2. **Use the 32 channels as packed independent series**, labelling them as `groups` (for example 32 singletons, or small groups that really are coupled). Most eval windows are univariate, and copied or spuriously coupled channels hurt.
3. **Make throughput the first engineering goal:** vectorised numpy or numba, L=4096, and comfortably above 290k values/s per core under 2 GB memory and a single thread.
4. **Match the pool:** daily-and-faster cadences with multi-seasonality (24/168, 288, 7); long-horizon structure (h=720 is a third of the score); held, flat and step regimes; intermittent counts; and realistic short contexts.
5. **Look for broad gains across many source families**, not big wins in one domain. That is what the cluster bootstrap rewards.
6. **Don't overfit the private pool.** The four-suite benchmark veto can still block a win.
7. **Local held-out data:** retired pool snapshots are published on HF (`Tensor-Link/cascade-eval-pool`, ~48 h lag). Use them with `cascade iterate --pool-dir`.
8. **Iterate cheaply** on the 17.58M/69M presets (`scripts/pyramid_config.py`). Confirm with clear multi-seed wins before spending the one-time submission.

## 8. Pre-submission checklist

- [ ] A fresh hotkey registered on netuid 91; a GPU-provider key in the environment
- [ ] `cascade verify DIR --live --json` passes under WSL2/Linux; also check with `--chain-toml chain.testnet.toml`, which rejects packed code
- [ ] A throughput test that proves 50B points in 90 min on 32 single-core children at 2 GB each
- [ ] Production-sized seeds (≥ 2^32) work and the output is deterministic
- [ ] Clear multi-seed local wins on a real held-out pool
- [ ] Explicit human go-ahead before `submit` / `fund --yes`
