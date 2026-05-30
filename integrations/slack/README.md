# Slack adapter (reference)

The Slack adapter is the reference implementation of the iris adapter
contract. It runs in two modes:

| Mode | What | Entry point |
|---|---|---|
| Outbound notifier | One-shot POST to a webhook URL | `scripts/notify-slack.sh` (called by `scripts/notify.py`) |
| Bidirectional bot | Socket Mode listener | `scripts/slackbot-start.sh` → `python -m integrations.slack.app` |

## Required env vars

```bash
# Outbound notifier (optional — empty = no-op)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Bidirectional bot (required for slackbot-start.sh)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_CHANNEL_ID=C...    # restrict the bot; empty = listen everywhere
```

Set up at https://api.slack.com/apps — enable Socket Mode, install to a
workspace, copy the tokens. The bot needs `app_mentions:read`, `chat:
write`, `commands`.

## What the bot understands

- `@iris status` — `loop_status` + `tasks.open` + `current handover`
- `@iris tasks` — full backlog
- `@iris handover current` — current handover id + body excerpt
- `@iris handover list` — last 5 handover ids
- `@iris loop start|stop|status` — manage `claude -p "/run"` headless sessions
- Slash commands: `/iris-loop`, `/iris-tasks`, `/iris-handover` (mirror of the mention API)

## Smoke test

```bash
# 1. core works (no Slack involvement)
python3 scripts/doctor.py

# 2. client round-trips against the local iris primitives
python3 -c "from integrations.slack.client import loop_status; print(loop_status()['memory'])"

# 3. start the bot (foreground)
bash scripts/slackbot-start.sh
```
