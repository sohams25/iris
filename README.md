# iris

**Claude Code-native workflow plugin.** Drops into any Claude Code project
and adds persistent memory across sessions, a backlog-driven execution
loop, parallel swarm waves, hooks for the moments that matter, and a
connect-to-anything integration layer.

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude Code session                                            │
│                                                                 │
│  ┌────────────────┐    ┌─────────────────┐    ┌──────────────┐  │
│  │ slash commands │ →  │ scripts/*.py    │ →  │ memory       │  │
│  │ .claude/cmds/  │    │ (memory, plan,  │    │ markdown │   │ │
│  └────────────────┘    │  doctor, swarm) │    │ obsidian     │  │
│  ┌────────────────┐    └─────────────────┘    └──────────────┘  │
│  │ hooks          │           ↑                       ↑         │
│  │ .claude/hooks/ │           │                       │         │
│  └────────────────┘    ┌──────────────────────────────────┐     │
│  ┌────────────────┐    │  integrations/<adapter>/         │     │
│  │ skills         │ ←  │   slack (ships) · discord (stub) │     │
│  │ .claude/skills/│    │   webhook (stub) · email (stub)  │     │
│  └────────────────┘    └──────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## What it gives you

| Feature | How |
|---|---|
| **Memory across sessions** | A handover file is written automatically when context compaction fires. The `SessionStart` hook loads the current handover at the top of every new session. |
| **Backlog-driven execution** | `docs/plan.md` is YAML-front-matter. `/run` works it serially (one task → verify → commit → loop). `/swarm` fans file-disjoint tasks across parallel Agent-tool waves. |
| **Commit-message guard** | A `PreToolUse(Bash)` hook blocks `git commit` messages containing `🤖 Generated with Claude Code`, `Co-Authored-By: Claude`, and similar AI footers. Backed by a `commit-style` skill that documents the voice. |
| **Connect-to-anything** | An adapter shape under `integrations/<name>/`. Slack ships as the reference adapter. Discord, webhook, and email are documented stubs. |
| **Doctor** | `scripts/doctor.py` runs 14 health checks (CLI present, plan valid, hooks executable, settings.json valid, skill symlinks resolve, etc.) and exits 0/1 — wireable to CI. |

## Quickstart

Iris is designed to live alongside an existing Claude Code project. Pick
the project you want to add iris to.

```bash
git clone https://github.com/sohams25/iris.git ~/Tools/iris
cd <your-project>
bash ~/Tools/iris/setup.sh
```

`setup.sh` does this:

1. Symlinks `.claude/{commands,hooks,skills}/` and `scripts/` into your
   project. The plugin surface is owned by iris; your project owns its
   own `CLAUDE.md` and `docs/plan.md` (templates copied if missing).
2. Generates `.env` from `.env.example` if not present.
3. Offers to install [obsidian-mind](https://github.com/obra/obsidian-mind),
   [superpowers](https://github.com/obra/superpowers), and
   [stop-slop](https://github.com/hardikpandya/stop-slop) as
   `~/Tools/<name>/` clones (or symlinks).
4. Runs `python3 scripts/doctor.py` and prints the verdict.

Open a Claude Code session in the project; `/status` confirms install.

## Commands

| Command | What it does |
|---|---|
| `/status` | Snapshot: open tasks, current handover, branch, last commits |
| `/backlog [Tnnn]` | Full backlog table; optionally one task by id |
| `/submit <desc>` | Refine a raw description into a `T###` entry in `docs/plan.md` |
| `/run` | Serial loop: next task → implement → verify → commit → loop |
| `/swarm` | Parallel-wave execution via the Agent tool (file-disjoint tasks only) |
| `/rollover [title]` | Manual handover checkpoint with carry-forward |
| `/memory [current\|list\|search\|validate]` | Inspect the memory backend |
| `/doctor` | Run the 14 health checks |
| `/new-task <slug>` | Scaffold `$PROJECTS_DIR/<N>_<slug>/` with template README + docs/ + archive/ |

`/plan` is reserved by Claude Code's built-in plan mode. Use `/backlog`.

## Hooks

| Event | Script | What it does |
|---|---|---|
| `SessionStart` | `.claude/hooks/session-start.sh` | Reads `memory.py current` and injects the handover body as a `## iris context` block |
| `PreCompact` | `.claude/hooks/pre-compact.sh` | Auto-runs `/rollover` semantics. Writes a new handover before Claude compacts. |
| `PreToolUse(Bash)` | `.claude/hooks/block-ai-commit-trailers.sh` | Blocks `git commit` whose message body contains an AI signature. Fails open on any malformed input. |

All three are wrapped so they never block a session if the underlying
script breaks.

## Memory backends

| Backend | Storage | When to use |
|---|---|---|
| `markdown` (default) | `handovers/handover_NNN.md` at repo root | Zero external deps. Plain files. Easy to grep. |
| `obsidian` | `$OBSIDIAN_VAULT/work/handovers/<date>__<slug>.md` | You already use Obsidian and want handovers searchable from your vault. |

Switch via `MEMORY_BACKEND` in `.env`. `scripts/migrate-handovers.py`
moves an existing markdown corpus into a vault, preserving the prev/next
chain via `[[wikilinks]]`.

## Integrations — the connect-to-anything model

```
integrations/
├── slack/       # reference adapter (ships)
├── discord/     # documented stub
├── webhook/     # documented stub
└── README.md    # adapter contract
```

Each adapter is a small Python package with a `start()` entry point
and its own env-var contract. The core has no idea Slack exists — it
just exposes `scripts/memory.py`, `scripts/parse-tasks.py`, and the
slash commands. An adapter wraps those for its medium.

To add a new adapter, copy `integrations/slack/` to
`integrations/<your-name>/`, retarget its sender/receiver, and add the
env-var stub to `.env.example`. See `integrations/README.md` for the
contract and `docs/integrations.md` for a worked example.

## Layout

```
iris/
├── .claude/
│   ├── commands/     # slash commands (9 files)
│   ├── hooks/        # 3 hooks: session-start, pre-compact, block-ai-trailers
│   ├── skills/       # 3 owned skills: handovers, swarm, commit-style
│   └── settings.json # hook wiring
├── scripts/
│   ├── memory.py     # CLI over the memory backends
│   ├── doctor.py     # 14 health checks
│   ├── parse-tasks.py# YAML backlog parser
│   ├── handover-new.py + handover-validate.py
│   ├── migrate-handovers.py
│   ├── build-wave-plan.py  # swarm-wave dependency planner
│   ├── notify.py + notify-slack.sh
│   ├── detect-verify.sh    # auto-detect the verify command
│   └── slackbot-start.sh
├── integrations/
│   ├── slack/        # the reference adapter
│   ├── discord/      # stub
│   └── webhook/      # stub
├── tests/            # pytest — primitives + hooks + adapter contract
├── docs/
│   ├── plan.md             # template backlog
│   ├── integrations.md     # adapter authoring guide
│   └── architecture.md     # how the pieces fit
├── .env.example
├── CLAUDE.md         # the agent guide
├── setup.sh          # one-command install into a target project
├── Makefile
├── pyproject.toml
└── README.md
```

## Why iris?

Greek messenger goddess. The rainbow bridge between worlds — between
your Claude session and your terminal, your handovers and your future
sessions, your backlog and your team's chat. The "connect to anything"
brief made the name pick itself.

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgements

- [obsidian-mind](https://github.com/obra/obsidian-mind) — the vault
  format that the obsidian memory backend writes against.
- [superpowers](https://github.com/obra/superpowers) — skills that iris
  symlinks in if you install them.
- [stop-slop](https://github.com/hardikpandya/stop-slop) — MIT;
  iris's `commit-style` skill defers to it on prose voice.
- [Claude Code](https://docs.anthropic.com/claude/claude-code) — the
  host. Iris is just plumbing; the agent does the work.
