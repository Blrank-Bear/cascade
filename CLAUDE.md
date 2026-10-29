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
