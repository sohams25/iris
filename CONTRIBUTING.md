# Contributing to iris

Thanks for considering a PR.

## Setup

```bash
git clone https://github.com/sohams25/iris.git
cd iris
pip install -e ".[dev]"
make test
```

## What's in scope

- New integration adapters (Discord, Teams, email, queues). See
  `docs/integrations.md`.
- New slash commands that fit the workflow plugin shape (read-only
  reports, lightweight scaffolding). No replacing Claude's own slash
  commands.
- New hooks for events Claude Code exposes (PreCompact, SessionStart,
  PreToolUse, PostToolUse, Stop).
- New memory backends (SQLite, Postgres, a git-tracked vault).
- Improvements to `doctor.py`'s checks.

## What's out of scope

- Anything that requires running iris as a daemon. The plugin shape is
  intentionally daemonless.
- Anything that depends on a specific cloud (AWS, GCP, etc.).
- Re-implementing Claude Code's own surface (its plan mode, its skill
  loader, its agent harness).

## Style

The `commit-style` skill ships in this repo. Read
`.claude/skills/commit-style/SKILL.md` before opening a PR. Briefly:

- Subject: `<type>: <terse outcome>`. Types: feat, fix, refactor, perf,
  docs, chore, test.
- Body: explain the **why**. The diff explains the what.
- No AI footers. The PreToolUse hook in this repo blocks them locally,
  but CI also greps for them.

## Tests

- New scripts: add a `tests/test_<script>.py`.
- New hooks: add a `tests/test_<hook>.py` with at least one block path
  and one allow path.
- New adapters: see `docs/integrations.md` section 5.

## Doctor

Any new feature that has a misconfiguration mode should add a check to
`scripts/doctor.py`. Each check is a `(name, fn)` tuple; `fn` returns
`(bool, str)`.
