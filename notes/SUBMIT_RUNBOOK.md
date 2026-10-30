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
