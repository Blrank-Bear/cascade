# Working generator

Base: Lane A reign-13 king `716765dcf2f6`, the first v2 king (unchanged copy in
`reference/kings/2026-11-04-716765dcf2f6/`). Our previous c251-based codebase, with its
switchable feature layers, is kept in `generator_c251/` for porting.

- The outermost class `Generator` is the king's LCP-LATE layer. It yields
  `{"values": (32, 4096) float64, "groups": uint8[32]}`.
- Our layers are appended (never prepended), switchable and off by default (see CLAUDE.md).

Checks (WSL):
- `tests/golden/run_k13.sh check`: byte-identical regression (natural, plus late with the cooldown switch).
- `tests/v2/validate.py generator`: v2 validator policy, determinism, duplicates.

Not yet a submission.
