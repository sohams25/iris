#!/usr/bin/env bash
# Compatibility shim that delegates to scripts/notify.py.
#
# Preserves the original interface:
#   notify-slack.sh "title" "body"
#
# notify.py prefers posting as the bot user (chat.postMessage) when
# SLACK_BOT_TOKEN + SLACK_CHANNEL_ID are set, and falls back to the
# incoming webhook otherwise. No-op when neither is configured.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TITLE="${1:-Notification}"
BODY="${2:-}"

# notify.py picks bot vs webhook on its own.
exec python3 "$ROOT/scripts/notify.py" "$TITLE" "$BODY"
