---
description: Inspect the active memory backend — current / list / search / validate.
---

Parse `$ARGUMENTS`. The first word is the subcommand (default `current` if empty).

| First word | Shell call |
|---|---|
| `current` | `python3 scripts/memory.py current` (print full body) |
| `list`    | `python3 scripts/memory.py list` |
| `validate`| `python3 scripts/memory.py validate` |
| `search`  | `python3 scripts/memory.py search "<remaining words>"` |

Format the output for readability:
- Strip ANSI if present.
- For `current`, the body is already markdown — render it inline.
- For `list`, the output is already a table — render as-is.
- For `search`, present hits as a bullet list with id in monospace and snippet truncated to ~140 chars.
- For `validate`, surface any issues prominently.

If the first word doesn't match any of the above, show the help line:
```
usage: /memory [current|list|search <query>|validate]
```
