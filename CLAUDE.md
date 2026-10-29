# Workspace rules

- All work happens inside this folder (`D:\CODE\Bittensor\cascade\cascade`).
- Do NOT write to the system temp dir, `/tmp`, or the session scratchpad.
  - Temporary files (scripts, intermediate outputs, downloads): `.claude-work/tmp/`
  - Session notes / memory / logs: `.claude-work/session/`
- `.claude-work/` is git-ignored.

# Git rules

- Commit after every change you make.
- Author and committer must be only `Blrank-Bear <owijihexexim57@gmail.com>` (set in local git config).
- No `Co-Authored-By` or other attribution lines in commit messages.

# Layout

- `upstream/` — clone of https://github.com/TensorLink-AI/cascade (branch `cascade-v2`), subnet 91. Git-ignored; update with `git -C upstream pull`. Don't commit changes there.
- Own miner/generator code lives in this repo, outside `upstream/`.
- `reference/kings/` — exported king generators (study only; never run outside a sandbox, never copy into a submission).
- `notes/` — analysis notes.

# Refactoring rules

- When refactoring, break every function down so each one performs a single, atomic unit of functionality.
- More code and more functions is accepted; the goal is that each bug fix or performance change maps to exactly one small function.
- Refactors must preserve behavior (verify with golden-output / digest tests before and after).

# Update rules

- Organize updates by specific functionality (one feature = one clearly named block/section).
- Implement updates by ADDING new methods/functions/classes. Do not modify or delete existing methods: existing code may be relied on elsewhere.
- Prefer wrapping (new outer layer, new subclass, new helper called from a new path) over editing existing code. Make new behaviour switchable from config where possible.
- The atomic-function refactoring rule applies only when explicitly refactoring.
