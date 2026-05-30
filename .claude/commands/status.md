---
description: Compact snapshot — backlog counts, current handover, branch, last commits.
---

Print a snapshot. Run these in order, no agents:

1. `python3 scripts/parse-tasks.py list` — parse JSON. Count open (`passes==false && blocked==false`), blocked, passed.
2. Find the next task: filter for open, sort by priority asc then id asc, pick first.
3. `python3 scripts/memory.py current --id-only` — current handover id.
4. `git rev-parse --abbrev-ref HEAD` and `git rev-parse --short HEAD` and `git status --short` (count lines for dirty marker).
5. `git log -5 --oneline`.
6. If `.swarm-locks.json` exists at the repo root, surface it.

Format:

```
Backlog: <O> open · <B> blocked · <P> done    (next: T### — <title>)
Handover: <id>
Branch: <branch> @ <short-sha>   <clean|dirty (N)>
Recent:
  <short-sha>  <subject>
  ...
```

If a swarm lock is active, append:

```
⚠ swarm run in progress (wave <N>, started <iso-ts>)
```
