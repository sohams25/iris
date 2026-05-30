---
description: Run docs/plan.md tasks in parallel waves via the swarm orchestrator.
---

Invoke the `swarm` skill to execute the backlog at `docs/plan.md` (or
`$ARGUMENTS` if a path is given).

Use the Skill tool with `skill: "swarm"` to begin. The orchestrator will:

1. Build the wave plan via `scripts/build-wave-plan.py`.
2. Show me the planned waves and ask me to confirm before launching.
3. Run each wave's tasks in parallel using the Agent tool.
4. Verify between waves and commit on green.
5. Notify Slack on completion.

Arguments (optional): path to an alternate plan file. Defaults to `docs/plan.md`.
