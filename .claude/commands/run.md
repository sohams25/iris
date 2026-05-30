---
description: Work the backlog in docs/plan.md serially — one task at a time, verify between.
---

Work the open backlog at `docs/plan.md` serially until empty or the user stops you.

Optional arguments via `$ARGUMENTS`: `max_iterations=N`, `max_minutes=M`, `dry_run=true`. Parse them yourself; defaults are 50 / 480 / false.

For parallel execution within a wave, use `/swarm` instead — that invokes the existing `swarm` skill which spawns Agent-tool subagents per wave. This command is the **supervised serial loop**.

## Loop body

Cache the verify command at the top of the loop:

```bash
bash scripts/detect-verify.sh
```

Then for each iteration:

1. **Pick the next task:** `python3 scripts/parse-tasks.py next` returns JSON of the next open, unblocked task in priority order. If output is empty, you're done — print `backlog empty` and stop.

2. **Announce it:** show id, title, files. If `--dry-run` mode (the `dry_run=true` arg), mark passes and skip steps 3-6.

3. **Implement it yourself** using Read, Edit, Write, Bash. Stay within the declared `files:` list when one exists. Do NOT modify `docs/plan.md` during implementation.

4. **Run verify:** `bash -c "$VERIFY_CMD"`. Capture stdout+stderr (last 4 KB).

5. **On green:**
   - `python3 scripts/parse-tasks.py mark <id> passes true`
   - Author a commit. Invoke the `commit-style` skill first to set the
     voice and trailer rules; default scaffold is
     `feat(<id>): <terse outcome>` with a 1-3 line body explaining the
     why if the change is more than mechanical.
   - `git add -A && git commit -F <message-file>` (skip if no changes).
   - `bash scripts/notify-slack.sh "<id> passed" "<title>" || true`

6. **On red — retry up to 2 times** by re-reading the verify output and fixing. If still red:
   - `python3 scripts/parse-tasks.py mark <id> blocked true`
   - `python3 scripts/parse-tasks.py note <id> "blocked by verify; tail: <last 400 chars>"`
   - `bash scripts/notify-slack.sh "<id> blocked" "<reason>" || true`

7. **Loop.**

## Stop conditions (any one)

- Backlog empty.
- Iteration count exceeds `max_iterations` (default 50).
- Wall-clock minutes exceeds `max_minutes` (default 480).
- 3 consecutive iterations with no new commit (circuit breaker).
- User says stop.
- PreCompact hook fires (it will write a fresh handover; next session picks up from it).

## Rules

- Do NOT skip verify between tasks.
- Do NOT skip committing on green — the loop's state lives in git history.
- Do NOT continue past 3 stagnant iterations; abort and Slack-notify.
- If the verify command is the fallback (`echo 'no verify command…'`), warn the user once at the top of the loop. Tasks will appear to pass automatically — that's intentional but may not be what you want.
