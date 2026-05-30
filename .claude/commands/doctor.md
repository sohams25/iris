---
description: Run scripts/doctor.py and surface the result.
---

Run:
```
python3 scripts/doctor.py
```

Present the output verbatim. The script's exit code is 0 if all checks pass, 1 if any fail.

If any check fails, follow up with a one-line suggestion per failing check:

| Failing check | Suggested remedy |
|---|---|
| `claude CLI` | Install Claude Code or add it to PATH. |
| `docs/plan.md` | `cat docs/plan.md` and check YAML front-matter delimiters. |
| `memory current` | `/rollover` to create one. |
| `memory backend` | Check `MEMORY_BACKEND` and `OBSIDIAN_VAULT` in `.env`. |
| `scripts/` | Run `git status` — one of the helper scripts was deleted. |
| `hooks` | `ls -la .claude/hooks/` then `chmod +x .claude/hooks/*.sh`. |
| `settings.json` | `python3 -c "import json; json.load(open('.claude/settings.json'))"` to find the parse error. |
| `slash commands` | Restore the missing markdown files from git history. |
| `CLAUDE.md` | Restore from git history; auto-loaded as project context. |
| `slack config` | Fill in `.env` from `.env.example`. |
| `verify cmd` | Add `scripts/verify.sh` or set `VERIFY_CMD` env var. |
| `git` | Run from inside the repo. |

Do not attempt to fix issues automatically — print suggestions and let the user decide.
