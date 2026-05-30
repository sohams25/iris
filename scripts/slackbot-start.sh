#!/usr/bin/env bash
# Boot the Slack bot. Reads tokens from .env.
# The bot shells out to scripts/*.py per request — no separate backend needed.
#
# Usage:
#   ./scripts/slackbot-start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "[slackbot-start] ERROR: .env not found at $ROOT/.env" >&2
  echo "Copy .env.example to .env and fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID." >&2
  exit 1
fi

VENV=".iris-state/.venv"
if [[ ! -d "$VENV" ]]; then
  echo "[slackbot-start] creating venv at $VENV..."
  mkdir -p .iris-state
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
fi

if ! "$VENV/bin/python" -c "import slack_bolt" 2>/dev/null; then
  echo "[slackbot-start] installing slack-bolt + slack-sdk + pyyaml..."
  "$VENV/bin/pip" install --quiet slack-bolt slack-sdk pyyaml
fi

echo "[slackbot-start] starting Slack bot (Ctrl-C to stop)"
exec "$VENV/bin/python" -m integrations.slack.app
