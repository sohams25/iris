---
name: swarm
description: Parallel multi-agent task execution — the engine /run invokes when it routes to parallel. Reads docs/plan.md, builds a dependency graph by file overlap, and runs file-disjoint tasks in parallel waves via the Agent tool.
---

# swarm — parallel execution engine

This skill turns a flat task backlog into parallel agent execution. It is the
parallel engine `/run` invokes when `build-wave-plan.py --decide` routes to
parallel — **not** a user-facing slash command. Where `/run`'s serial loop
works one task at a time, the swarm runs **file-disjoint tasks in parallel
waves** using the `Agent` tool.

## When invoked

`/run` invokes this skill (Skill tool, `skill: "swarm"`) after it drains the
queue and `build-wave-plan.py --decide` returns `mode: parallel`. You are the
orchestrator for that parallel run.

## Inputs

- Default backlog: `docs/plan.md` (YAML front-matter with `tasks:` list).
- `/run` may pass an alternate plan path through to this skill.

## Execution protocol

You are the **orchestrator**. You do not implement tasks yourself — you
launch agents that implement tasks. Follow this protocol strictly:

### 1. Build the wave plan

Run:

```bash
python3 scripts/build-wave-plan.py
```

This emits JSON describing waves. Each wave contains tasks whose `files`
do not overlap. Tasks with no `files` declared (or with glob patterns) are
treated as **exclusive** and occupy their own wave — they run alone.

Display the wave plan to the user as a short summary:
- Total tasks
- Number of waves
- For each wave: task IDs and their declared files

### 2. Detect the verify command

Run:

```bash
bash scripts/detect-verify.sh
```

Remember the result. You will run it after each wave.

### 3. Write the lock file

Before launching a wave, write `.swarm-locks.json` at the repo root:

```json
{
  "wave": 1,
  "started_at": "<ISO-8601>",
  "locks": {
    "T001": ["src/auth.ts"],
    "T002": ["src/billing.ts"]
  }
}
```

This is advisory but documents intent. If a future iteration finds an
existing lock with `wave` matching the current attempt, treat it as a
crashed prior run and warn the user.

### 4. Launch the wave in parallel

For each task in the current wave, call the `Agent` tool. **All calls in
the wave go in a single message** so they execute concurrently.

Each agent prompt should look like:

> You are implementing task `<ID>: <Title>` from `docs/plan.md`.
>
> **Files in scope (the ONLY files you may modify):**
> - <file 1>
> - <file 2>
>
> **Constraints:**
> - Follow existing patterns in the codebase.
> - Do not modify any file outside the scope list.
> - Do not modify `docs/plan.md`.
> - Do not run the verify command yourself — the orchestrator will.
>
> When you finish, reply with a one-line summary of what you changed.

Use `subagent_type: ecc:code-architect` (or the most relevant specialist)
when the task domain matches; otherwise use the default `claude` agent.

### 5. Verify the wave

After all agents in the wave return, run the verify command from step 2.

- **Green:** mark every task in the wave as `passes: true` via
  `python3 scripts/parse-tasks.py mark <ID> passes true`. Commit:
  `git commit -m "feat(swarm wave <N>): <comma-separated IDs>"`.
- **Red:** identify which task's changes broke verify. If unclear, run
  `git diff` between waves. Mark the breaking task as `blocked: true`,
  revert ONLY that task's files (`git checkout HEAD~<n> -- <files>`),
  and re-run verify. Repeat until verify passes or the wave is abandoned.

### 6. Release locks, drain the queue, advance

Delete `.swarm-locks.json`, then `python3 scripts/queue.py drain` so anything
you queued into `docs/next.md` during the wave joins the backlog before the
next wave is planned. Proceed to the next wave; repeat steps 3–5.

### 7. Final report

When all waves complete (or are abandoned), report to the user:
- Tasks passed
- Tasks blocked (with reasons from `notes` field)
- Total wall-clock time
- Notify Slack: `bash scripts/notify-slack.sh "Swarm complete" "<summary>"`

## Safety rules

1. **Never have two agents edit the same file in the same wave.** The wave
   builder already enforces this; do not override.
2. **Never let an agent mark its own task complete.** Only the orchestrator
   marks `passes: true`, and only after verify is green.
3. **Never skip verify between waves.** Cascading silent failures will
   waste hours.
4. **If verify is undefined** (`detect-verify.sh` returns the fallback),
   stop and tell the user — running blind is worse than running serially.
5. **If a wave has only one task,** consider falling back to the serial
   loop for that task; the orchestration overhead is unnecessary.

## Output format

Print short progress lines as you go:

```
[swarm] wave 1/3: launching 2 agents (T001, T002)
[swarm] wave 1/3: agents returned (T001=ok, T002=ok)
[swarm] wave 1/3: verify green — committed
[swarm] wave 2/3: launching 1 agent  (T003 — exclusive: empty files[])
...
[swarm] complete: 5 passed, 0 blocked, 12m 04s
```

## Differences — serial /run vs parallel swarm

| Aspect | Serial /run | Swarm |
|---|---|---|
| Concurrency | Serial | Parallel within waves |
| Best for | Overnight unattended runs | Interactive sessions where you can supervise |
| Token cost | Lower | Higher (parallel sessions multiply) |
| Backlog | Same `docs/plan.md` | Same `docs/plan.md` |
| Commits | One per task | One per wave |
| File locks | Not needed | Required (advisory `.swarm-locks.json`) |
