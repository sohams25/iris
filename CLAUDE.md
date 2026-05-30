# iris — agent guide

Iris is a Claude Code-native workflow plugin. It gives a Claude Code
project four things that don't exist out of the box:

1. **Persistent memory across sessions** — handovers written by Claude
   itself, loaded automatically at session start.
2. **A backlog-driven execution loop** — `/run` works `docs/plan.md`
   serially; `/swarm` fans the same backlog out in parallel waves via
   the Agent tool.
3. **Hooks for the moments that matter** — `SessionStart` (auto-load
   the current handover), `PreCompact` (snapshot before context
   compaction), `PreToolUse(Bash)` (block AI-trailer commit messages).
4. **An integrations layer** — a "connect to anything" adapter shape so
   the same workflow drives Slack today, Discord / email / webhooks
   tomorrow. Slack ships as the reference adapter.

This file is the canonical agent guide. The `SessionStart` hook reads
the current handover and injects it on top of every new session.

## Standing instructions

These belong to your project, not iris. Replace the bullets below with
your own do / do-not rules. They are carried forward into every
handover automatically.

- _<add your standing rules here — e.g. "do not push to main without a
  reviewer", "all secrets go through 1Password", "tests live under
  `tests/integration/`">_

## Tone and voice

Optional. If you and your team have a preferred commit / handover voice,
encode it here so handovers and commits respect it. Default is "engineer
typing into a terminal at the end of a focused hour."

## Where things live

| Concern | Path |
|---|---|
| Backlog | `docs/plan.md` (YAML front-matter + prose) |
| Handovers (obsidian) | `$OBSIDIAN_VAULT/work/handovers/` if `MEMORY_BACKEND=obsidian` |
| Handovers (markdown fallback) | `handovers/handover_NNN.md` if `MEMORY_BACKEND=markdown` |
| Slash commands | `.claude/commands/*.md` |
| Skills | `.claude/skills/<name>/SKILL.md` |
| Hooks | `.claude/hooks/*.sh` + `.claude/settings.json` |
| Scripts | `scripts/*.py` and `scripts/*.sh` |
| Integration adapters | `integrations/<name>/` (slack ships, discord+webhook stubbed) |
| Event log | `.iris-state/events.jsonl` (markdown backend only) |
| Run lock | `.iris-state/run.lock` (PID of active `claude -p "/run"`) |

## Slash commands

| Command | Purpose |
|---|---|
| `/status` | Snapshot: backlog counts, current handover, branch, last commits |
| `/backlog [Tnnn]` | Full backlog readout, optionally focused on one task |
| `/submit <description>` | File a new T### into `docs/plan.md` (refines first) |
| `/run` | Serial loop: next task → implement → verify → commit → loop |
| `/swarm [plan.md]` | Parallel-wave execution via the Agent tool. File-disjoint tasks only |
| `/rollover [title]` | Manual handover checkpoint with carry-forward |
| `/memory [current\|list\|search\|validate] [...]` | Inspect the memory backend |
| `/doctor` | Run `scripts/doctor.py` (14 health checks) |
| `/new-task <kebab-name>` | Scaffold `$PROJECTS_DIR/<N>_<name>/` with README + docs/ + archive/ |

Do not call `/plan` — Claude Code's built-in plan mode reserves it.

## Memory backends

`MEMORY_BACKEND=markdown` is the default. Handovers go into
`handovers/handover_NNN.md` at the repo root. Zero external
dependencies.

`MEMORY_BACKEND=obsidian` writes into `$OBSIDIAN_VAULT/work/handovers/`
instead. The vault must exist; iris does not create it. Use this when
you want handovers searchable from Obsidian alongside the rest of your
notes.

The `PreCompact` hook auto-runs `/rollover` semantics when Claude is
about to compact context. That's the real context-pressure signal —
you do not need to guess from iteration counts.

## Coding standards

Defaults, override in your project:

- Semantic variable names.
- No AI preambles in commits or comments.
- Every code change followed by a terminal verification command.
- Only the user signals task completion — do not declare a task done
  yourself; the verify gate and `/run`'s mark/commit step do that.

## Skills available

Project-local skills under `.claude/skills/`:

- `handovers/` — handover frontmatter contract and writing rules.
- `swarm/` — parallel-wave execution protocol.
- `commit-style/` — human-voice commit messages; forbids AI footers.

Optional skills that iris's `setup.sh` can symlink in if you have them
installed at `~/Tools/`:

- `superpowers` skills (brainstorming, dispatching-parallel-agents,
  executing-plans, finishing-a-development-branch, receiving-code-
  review, requesting-code-review, subagent-driven-development,
  systematic-debugging, test-driven-development, using-git-worktrees,
  using-superpowers, verification-before-completion, writing-plans,
  writing-skills) — from https://github.com/obra/superpowers.
- `stop-slop` — from https://github.com/hardikpandya/stop-slop. MIT.

`scripts/doctor.py`'s skill-symlinks check surfaces any broken symlinks.

## Plugin-portable settings

Iris exposes its conventions as environment variables. Override in `.env`:

| Var | Default | Effect |
|---|---|---|
| `MEMORY_BACKEND` | `markdown` | Selects which storage `scripts/memory.py` writes through |
| `OBSIDIAN_VAULT` | (unset) | Vault root when `MEMORY_BACKEND=obsidian` — must exist |
| `PROJECTS_DIR` | `Tasks` | Root directory `/new-task` scaffolds into |
| `PLAN_PATH` | `docs/plan.md` | The serial-execution backlog |
| `CLAUDE_BIN` | `claude` | Override if multiple Claude Code CLIs are installed |
| `IRIS_STALE_PATH_IGNORE` | (unset) | Colon-separated path prefixes the stale-reference scanner ignores |

## When something is unclear

- Read the current handover (`/memory current` or look at the
  SessionStart injection).
- For prior decisions: `/memory search "<keyword>"`.
- Ask the user. Do not invent or guess.
