---
description: Autonomous takeover — toggle hands-off, self-directing work driven by the second brain.
---

`/takeover on|off|status`. When **on**, iris runs unattended: it decides the
next objective itself (it may invent goals, not just drain the backlog),
consults the **second brain** to simulate what you'd choose, executes via
`/run`, learns from the outcome, and loops — no per-step confirmation. The
guardrails that always stay: verify-before-commit, the `/takeover off`
kill-switch, the cycle/time budgets, and a full audit trail.

Parse `$ARGUMENTS`: `on` / `off` / `status`, plus optional `budget_cycles=N`,
`budget_minutes=M`.

## `/takeover off`

```bash
python3 scripts/takeover.py off --reason "user"
```
The running loop stops at its next `step`. Print the confirmation and end.

## `/takeover status`

```bash
python3 scripts/takeover.py status
python3 scripts/brain.py status
```
Show takeover state + the top instincts the brain has learned. End.

## `/takeover on` — the autonomous loop

1. **Arm it:**
   ```bash
   python3 scripts/takeover.py on --budget-cycles <N|50> --budget-minutes <M|480>
   ```

2. **Each cycle:**

   1. **Gate (poll the kill-switch + budgets).** Pass last cycle's commit count
      as progress (0 on the first cycle):
      ```bash
      python3 scripts/takeover.py step --progress <commits-last-cycle>
      ```
      Exit code 3 (or `stop: …`) → announce the reason and **end the loop**.
   2. **Observe** the project: `/status`, `git status`, `parse-tasks.py list`,
      the current handover.
   3. **Simulate your choice.** For each real decision (what to build next, how
      to prioritize, style calls), ask the brain first:
      ```bash
      python3 scripts/brain.py simulate --domain <objective|priority|commit-style|…> --context "<situation>"
      ```
      Weight a high-confidence instinct heavily; on a miss, decide on first
      principles and you'll teach the brain in step 6.
   4. **Decide + record.** Choose the next objective (invent one from project
      state + brain if the backlog is thin). Write the audit
      `.iris-state/takeover/cycle-<N>.md` (objective + the simulated picks you
      used) and `python3 scripts/takeover.py log "<one-line decision>"`.
   5. **Decompose + execute.** Add tasks (`parse-tasks.py add` / `queue.py`),
      then run them through `/run` — it auto-routes serial vs parallel and
      **verifies + commits each step** (never skip verify).
   6. **Learn from the outcome (RL).** Reward the instincts that drove the
      decisions by how it went:
      ```bash
      python3 scripts/brain.py reward <instinct-id> <r>   # r=+1 verify green & kept · -1 reverted/undone
      ```
      Distil any new preference you saw in the user's past prompts or your own
      choices: `python3 scripts/brain.py observe --domain <d> --pattern "<…>"`.
      Every few cycles, `python3 scripts/brain.py decay` (graceful forgetting).
   7. **Loop** back to step 1.

## Rules

- **Never skip verify**, and never commit red — the loop's state is in git.
- The brain **guides** but does not gate: you may override a low-confidence
  instinct; record the override as a fresh `observe` so it learns.
- Stop the moment `step` says so (kill-switch, cycle/time budget, or 3
  stagnant cycles). Surface the reason and the cycle audit.
- Everything the loop decides is in `.iris-state/takeover/` — review it anytime.
