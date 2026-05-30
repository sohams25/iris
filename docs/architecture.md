# Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Claude Code session (the host)                                     │
│                                                                     │
│  ┌──────────────┐    ┌────────────────────┐    ┌─────────────────┐  │
│  │ User typing  │ →  │ Claude (the model) │ →  │ Tools           │  │
│  │ /commands    │    │ + system prompt    │    │ Bash, Read,     │  │
│  └──────────────┘    │ + skills           │    │ Edit, Write,    │  │
│                      │ + hooks            │    │ Agent           │  │
│                      └────────────────────┘    └─────────────────┘  │
│                              ↓ shells out                           │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ iris scripts (subprocess targets)                              │ │
│  │                                                                │ │
│  │  memory.py     parse-tasks.py     doctor.py     notify.py      │ │
│  │     ↓               ↓                                          │ │
│  │  ┌──────────────┐  ┌─────────────────┐                         │ │
│  │  │ memory       │  │ docs/plan.md    │                         │ │
│  │  │ markdown │   │  │ (YAML backlog)  │                         │ │
│  │  │ obsidian     │  └─────────────────┘                         │ │
│  │  └──────────────┘                                              │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              ↑ subprocess
                   (when running headless via slack / discord)
┌─────────────────────────────────────────────────────────────────────┐
│  integrations/<name>/                                               │
│  app.py → client.py → subprocess.run(["python3", "scripts/..."])    │
└─────────────────────────────────────────────────────────────────────┘
```

## Key boundaries

1. **The core does not know about adapters.** The slash commands, hooks,
   and scripts work identically whether or not Slack is configured.
2. **Adapters do not import iris Python modules.** They `subprocess`
   into `scripts/*.py`. This means an adapter survives any iris
   internal-API change as long as the CLI contract is stable.
3. **Hooks are advisory.** Every hook is wrapped to exit 0 (fail open)
   so a broken hook never blocks a session. The PreToolUse(Bash)
   commit-trailer hook is the one exception: it exits 2 to block, but
   only when its python3 verdict is "BLOCK"; any malformed payload
   falls open.
4. **State is on disk.** The lock file (`.iris-state/run.lock`), the
   event log (`.iris-state/events.jsonl`), and the handovers are all
   inspectable with `cat`. No daemon, no server, no in-memory state
   that disappears if you kill a process.

## Failure modes

| If this breaks | …this happens |
|---|---|
| `memory.py current` errors | `SessionStart` hook prints "no handover yet" and continues |
| `pre-compact.sh` errors | The hook logs to `.iris-state/logs/precompact.log` and exits 0 |
| `block-ai-commit-trailers.sh` errors | Fails open. Commits go through. |
| An adapter's env vars are missing | The adapter refuses to start. The core is unaffected. |
| `~/Tools/superpowers/` is moved | `doctor.py`'s skill-symlinks check fails. Iris's three owned skills still load. |
