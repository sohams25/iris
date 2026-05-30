---
description: Refine a raw task description, file it into docs/plan.md as the next T### entry.
---

The user wants to submit a new task to `docs/plan.md`. Their raw description is:

    $ARGUMENTS

Do this without launching agents:

1. Run `python3 scripts/parse-tasks.py list` and parse the JSON. Find the next available `T###` id (largest used `Tnnn` + 1, zero-padded to 3 digits).
2. Refine the raw description into a structured task:
   - **title** — one line, noun-phrase or imperative ("Wire CSP headers", "Fix login redirect"). Strip filler.
   - **files** — list of paths the task will touch. Use Grep/Glob to confirm they exist if you can name them. If the scope is coordination / investigation, leave `files: []`.
   - **priority** — integer. Default 5. If user said "urgent" / "now" / "P1", use 1.
   - **notes** — 2-6 lines explaining acceptance criteria and any obvious constraints.
3. Append the task via `python3 scripts/parse-tasks.py add --id T### --title "..." --priority N --files "a,b,c" --notes "..."`.
4. Print a one-line summary:

   ```
   submitted T### (P<priority>): <title>
   files: <comma-separated or none>
   ```

Do NOT run verify, commit, or notify Slack. Submission is intentionally cheap.
