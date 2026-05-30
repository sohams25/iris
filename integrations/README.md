# Integrations — the connect-to-anything model

An iris adapter wraps iris's core (memory, backlog, doctor, slash
commands) for a specific medium: chat platform, email, webhook, queue.
The core has no knowledge of any adapter. Adding a new one does not
touch the core.

## Adapter contract

A `integrations/<name>/` directory must contain:

| File | Required | Purpose |
|---|---|---|
| `__init__.py` | yes | Marks the package |
| `config.py` | yes (incl. stubs) | Reads adapter-specific env vars, validates them, exports a `healthcheck()` |
| `client.py` | full adapter | Pure-Python adapter for the iris primitives — calls `scripts/memory.py`, `scripts/parse-tasks.py`, etc., via `subprocess`. **No medium-specific imports here.** |
| `app.py` or `start.py` | full adapter | The entry point. Wires the medium (Slack Socket Mode, a Discord client, a Flask webhook) to `client.py` |
| `handlers/` | no | Subdirectory for per-command/per-event handlers |
| `README.md` | yes | One page: what it does, the env-var contract, smoke-test instructions |

A **stub** adapter (`discord/`, `webhook/`) ships only `config.py` (with a
`healthcheck()` that reports `wired: false`) + a `README.md` — enough to be
discovered and contract-tested. `client.py` and the entry point are added when
the adapter is wired for real (as `slack/` is).

## Env-var contract

Each adapter:

1. Declares its env vars in `.env.example` under a clearly-labelled
   section.
2. **Refuses to start** when a required var is missing — but only when
   the adapter itself is started. The core must keep working when an
   adapter's vars are absent.
3. Uses a unique prefix (`SLACK_`, `DISCORD_`, `WEBHOOK_`) so two
   adapters can coexist in one `.env`.

## Lifecycle

```
.env → config.py → app.py.main()
                       ↓
                   client.py  ←—  subprocess.run(["python3", "scripts/memory.py", ...])
                       ↓
                medium (Slack/Discord/...)
```

The core scripts (`scripts/*.py`) are the *only* iris-internal API the
adapter touches. Adapters never reach into iris's Python modules
directly — that keeps the boundary clean and the adapter swappable.

## Adapters that ship

| Adapter | Status | Path |
|---|---|---|
| Slack (Socket Mode bot + webhook notifier) | **shipped** | `integrations/slack/` |
| Discord | stub — documented, not wired | `integrations/discord/` |
| Generic webhook (POST receiver) | stub — documented, not wired | `integrations/webhook/` |
| Email (SMTP outbound, IMAP inbound) | not started | _open invitation_ |

To add a new one, copy `integrations/slack/` to `integrations/<your-
name>/`, retarget the medium pieces, and update `.env.example`. PRs
welcome.

## Smoke test for any adapter

```bash
# 1. core works without the adapter
python3 scripts/doctor.py && echo "core OK"

# 2. adapter loads when its env vars are set
( cd integrations/<name>/ && python3 -c "from . import config; print(config.healthcheck())" )

# 3. medium round-trips
python3 -m integrations.<name>.app --selftest
```
