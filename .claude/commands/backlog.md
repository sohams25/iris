---
description: Show the backlog as a readable table — open, blocked, recently passed.
---

If `$ARGUMENTS` matches `^T\d{3}$`, print only that task's full record.

Otherwise:

1. `python3 scripts/parse-tasks.py list` → JSON.
2. Present three sections in markdown:

```
## Open  (sorted by priority then id)

| id | P | title | files (truncated) | notes (first line) |
|----|---|-------|-------------------|--------------------|

## Blocked

| id | title | first line of notes |
|----|-------|---------------------|

## Recently passed (last 5)

| id | title |
|----|-------|
```

- Truncate `files` after 50 chars.
- Truncate `notes` first line after 80 chars.
- If a section is empty, write `_(none)_` and skip the table.

Does not run verify, commit, or notify Slack.
