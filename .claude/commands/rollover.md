---
description: Manually create a handover checkpoint with carry-forward from the prior one.
---

The user wants an explicit handover. Title argument: `$ARGUMENTS` (may be empty).

1. Run:
   ```
   python3 scripts/memory.py create --title "$ARGUMENTS" --reason manual
   ```
   Stdout will be the new handover id (single line).

2. Print the path of the new handover and the prior one (now `status: superseded`). The stderr of `memory.py create` already lists both.

3. `bash scripts/notify-slack.sh "Handover created" "<new id> — <title>"`.

The new handover is the active context for any session that starts after this point — the `SessionStart` hook loads it.

Use this before:
- Closing the laptop for the day.
- Switching to a major new piece of work.
- Asking another agent / teammate to take over.

The `PreCompact` hook runs the same flow automatically when Claude is about to compact context, so you usually do not need to call `/rollover` manually mid-session.
