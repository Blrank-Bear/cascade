# Submission runbook (Lane A, v2)

Prepared 2026-10-30. Claude prepares and checks packages; **only the human runs `cascade submit`** (wallet, provider key, spend).

## 1. Packages

Built by `tools/submit/build_package.py PROFILE` into `submission/<profile>/generator/` (git-ignored, reproducible). `MANIFEST.json` next to it has the sha256 of every file and the git HEAD.

| Profile | Contents | Status |
|---|---|---|
| **j30** (recommended) | King lineage `04e22672` + v2 32-channel pack layer + `v2_jumps.json {"rate": 0.3}` | Passes the v2-contract verify (deterministic, corpus digest `86629ed7…`) and dedup |
| base (fallback) | Same without the jumps stage | Passes the v2-contract verify (`75a87d72…`) and dedup |

- **Evidence for j30 is weak:** CPU transfer proxy 0.2613 vs base 0.2641 over 4 seeds (about 1.4 SE). GPU duels at real scale haven't run yet. The 4090 can't fit the 120m model, so this needs an 80 GB GPU.
- **Dedup:** no tree, token, masked or `py_*` digest matches the king (`tools/submit/dedup_check.py`, using upstream's fingerprinting). Building on a published king is allowed (MINER.md §9).

## 2. Checks (`bash tools/submit/preflight.sh base j30`, report in `submission/PREFLIGHT.json`)

| Check | Expected |
|---|---|
| `verify_v2_contract`: full verify under upstream `[v2.training]` (shards mode) | **pass** |
| `dedup_vs_king` | **pass** |
| `verify_offline`, `verify_strict_guard` | **fail, by design.** Offline verify with no bound contract checks v1 ∩ v2, and v1 rejects the v2 `groups` field. The strict-guard run raises no packed-source finding |
| `verify_live` (`LIVE=1`) | Must **pass** before submitting: it proves the deployed contract is v2 |

## 3. Why the timing matters

`cascade submit` verifies before uploading:
- **With a provider key (funded):** it uses the live deployed contract. That passes once the live contract is v2.
- **Without a key (`--no-fund`), or while the live contract is still v1:** it checks v1 ∩ v2 and **refuses** (`groups` is reserved).
- **Burn risk:** an entry trained under the v1 contract would be rejected as our fault. So submit only after the live check passes.

## 4. Steps at launch (after 2026-10-30 12:00 UTC)

From WSL, with the cwd set to the repo:

```bash
LIVE=1 bash tools/submit/preflight.sh j30     # verify_live must be rc=0
cd upstream
../.claude-work/venv/bin/cascade preflight ../submission/j30/generator --lane a --hotkey <PUBLIC_SS58> --json
```

Then the human runs the following in their own shell, with the provider key in an env var and never pasted into chat:

```bash
export LIUM_API_KEY=...        # env only
../.claude-work/venv/bin/cascade submit ../submission/j30/generator https://submissions.cascadesub.net \
    --wallet-name <wallet> --wallet-hotkey <hotkey> --label <label> --yes
cascade reveal-status <PUBLIC_SS58> --watch
```

- **Before any re-submit,** re-run the preflight: the package must match `MANIFEST.json`.
- **Never edit `submission/` by hand.** Change the profile and rebuild.

## 5. Current package: ovft25 (2026-11-06, replaces j30 / base)

`submission/ovft25/generator/` (built from 5c8ed50, clean tree; `MANIFEST.json` beside it).

**Contents:**
- Current king 716765dc, refactored; goldens byte-identical.
- `v2_lcpr.json {"on": true}`: switch at yield 10837 under the live contract (5e10 points / 32 children, n = 24,414,064), identical to the king.
- `v2_ovl.json`: level/amp overlays 0.25/0.25 in the trunk phase, with 12 health/energy families muted.

**Evidence:**

| Check | Result |
|---|---|
| Screen vs king + lcpr | +0.98% (s0), +0.43% (s1), mean +0.71% |
| 4-suite bench gate | win rate 0.604 |
| Win needs (LCB > bar) | about 1.2-1.5% real gain |

**Review (2026-11-06):**

| Check | Result |
|---|---|
| Profile vs GPU-tested arm | identical switches |
| Package output vs tested generator copy (97e1bcc) | identical sha256 over 300 production yields |
| `verify` under upstream main `[v2.training]` (shards) | **pass**, deterministic, corpus digest `18fadee6…` |
| dedup vs current king 716765dc | **pass**, no identical digest. Containment 0.966 is allowed: published king code is never a private copy |
| requirements.txt / config.json | byte-identical to the king's (hash-locked) |
| throughput, 1 core, production n | 12.1-13.3 yields/s vs 2.21 needed; the king's behaviour gives 16.3 |
| peak RSS, 1500 yields | 878 MB (child limit 2048 MB) |
| `verify_offline` / `verify_strict_guard` | fail by design (v1 ∩ v2 rejects `groups`) |
| `verify --live` | **blocked by the network**, not the package. `status/v2.json` reports `launch_preflight: blocked` ("v2 worker image is not qualified for this release"), so `cascade submit` refuses with `live_status_unavailable` until the operator repins the image |

**Steps (human only; keys in env vars, never in chat):**
```bash
cd upstream
../.claude-work/venv/bin/cascade status --json | head        # wait until launch_preflight is no longer "blocked"
../.claude-work/venv/bin/cascade verify ../submission/ovft25/generator --live --json   # must be ok
../.claude-work/venv/bin/cascade preflight ../submission/ovft25/generator --lane a --hotkey <PUBLIC_SS58> --json
export LIUM_API_KEY=...
../.claude-work/venv/bin/cascade submit ../submission/ovft25/generator https://submissions.cascadesub.net \
    --wallet-name <wallet> --wallet-hotkey <hotkey> --label ovft25 --yes
../.claude-work/venv/bin/cascade reveal-status <PUBLIC_SS58> --watch
```
- Re-run the preflight first (`KING=$PWD/reference/kings/2026-11-04-716765dcf2f6 bash tools/submit/preflight.sh ovft25`) if anything changed. The package must match `MANIFEST.json`.
- One hotkey, one submission per round: an admission rejection spends that round.

### 5a. Re-check on upstream 1c8f6c4 (2026-11-06)

Upstream main moved to `1c8f6c4` (DEC-CA-0067 bundle: quantile-head verdict from the v2b switch era, `image_decoupled_feature = "v2b-b10591aa"`). Re-ran the v2-contract verify on the unchanged package: **pass**, same corpus digest `18fadee6…`, same file hashes. Log: `submission/ovft25/logs/verify_v2_1c8f6c4.json`. Live `launch_preflight` still `blocked` at 12:35 UTC. Local note: `git -C upstream config core.fileMode false` (WSL marks every file mode-changed and blocks `pull`).
