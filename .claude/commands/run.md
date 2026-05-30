---
description: Work the backlog — drains your plan-ahead queue, then auto-routes serial or parallel.
---

Work the open backlog at `docs/plan.md` until it's empty or the user stops you.
`/run` is the single entry point: it picks **serial** or **parallel** execution
itself, and it ingests anything you queue mid-run from `docs/next.md`.

Optional `$ARGUMENTS`: `max_iterations=N`, `max_minutes=M`, `dry_run=true`
(defaults 50 / 480 / false). Parse them yourself.

## 0. Setup (once, at the top)

```bash
python3 scripts/queue.py drain          # ingest anything already queued in docs/next.md
bash scripts/detect-verify.sh           # cache the verify command ($VERIFY_CMD)
python3 scripts/build-wave-plan.py --decide
```

The `--decide` JSON gives `mode` (`serial`|`parallel`), a `reason`, the
auto-derived `width`, and the `waves`. **Honor it**, with one override: if
`detect-verify.sh` returned the fallback (`no verify command…`), force
**serial** — running parallel blind is worse than running serially (warn the
user once).

- **mode = parallel** → go to **§2 Parallel**.
- **mode = serial** → go to **§1 Serial**.

## 1. Serial loop

For each iteration:

1. **Drain the plan-ahead queue** — `python3 scripts/queue.py drain`. This is
   the sync point: tasks you saved into `docs/next.md` while the previous task
   ran are folded into the backlog now, between tasks, never mid-task.
2. **Pick the next task:** `python3 scripts/parse-tasks.py next` → JSON of the
   next open, unblocked task by priority. Empty output → print `backlog empty`
   and stop.
3. **Announce** id, title, files. If `dry_run=true`, mark passes and skip 4-7.
4. **Implement it yourself** (Read/Edit/Write/Bash). Stay within the declared
   `files:` when present. Do NOT modify `docs/plan.md` during implementation.
5. **Verify:** `bash -c "$VERIFY_CMD"`; capture stdout+stderr (last 4 KB).
6. **On green:** `parse-tasks.py mark <id> passes true`; author a commit
   (invoke the `commit-style` skill first; scaffold `feat(<id>): <terse
   outcome>`); `git add -A && git commit -F <msg>` (skip if no changes);
   `bash scripts/notify-slack.sh "<id> passed" "<title>" || true`.
7. **On red — retry up to 2×** by re-reading the verify tail and fixing. Still
   red → `parse-tasks.py mark <id> blocked true`; `parse-tasks.py note <id>
   "blocked by verify; tail: <last 400 chars>"`; Slack-notify.
8. **Loop.** Re-evaluate `build-wave-plan.py --decide` every few tasks — if the
   queue brought in enough disjoint work, it may now say `parallel`; you may
   switch to §2 for the remaining backlog.

## 2. Parallel waves

Drain the queue first (`python3 scripts/queue.py drain`), then invoke the
`swarm` skill (Skill tool, `skill: "swarm"`). It re-runs `build-wave-plan.py`
on the freshly-drained backlog (already width-capped to the auto ceiling),
shows the wave plan, launches each wave's tasks as parallel Agent-tool
subagents, verifies and commits per wave, and drains the queue between waves.
The swarm skill is the parallel engine; `/run` is its only caller now.

## Stop conditions (any one)

- Backlog empty (and `docs/next.md` empty).
- Iterations > `max_iterations` (default 50).
- Wall-clock > `max_minutes` (default 480).
- 3 consecutive iterations / waves with no new commit (circuit breaker).
- User says stop.
- PreCompact hook fires (it writes a fresh handover; the next session resumes).

## Rules

- Never skip verify between tasks/waves. Never skip committing on green — the
  loop's state lives in git history.
- Never spawn two agents editing the same file in one wave (the wave builder
  prevents this; don't override).
- Never continue past 3 stagnant iterations; abort and Slack-notify.
