#!/usr/bin/env bash
# PreCompact hook — auto-create a rollover handover before Claude compacts context.
#
# Stdin is JSON like: {"trigger":"auto|manual","transcript_path":"..."}.
# We never block compaction — always exit 0. All output goes to a log file
# so it does not appear in Claude's stream.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 0

LOG="$ROOT/.iris-state/logs/precompact.log"
mkdir -p "$(dirname "$LOG")"

{
  echo "=== pre-compact $(date -Is) ==="

  # Read stdin to figure out the trigger; tolerate missing stdin.
  TRIGGER="unknown"
  if [ ! -t 0 ]; then
    PAYLOAD=$(cat 2>/dev/null || true)
    echo "stdin: $PAYLOAD"
    if [ -n "$PAYLOAD" ]; then
      TRIGGER=$(printf '%s' "$PAYLOAD" \
        | python3 -c 'import json,sys
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(d.get("trigger", "unknown"))
except Exception:
    print("unknown")' 2>/dev/null || echo "unknown")
    fi
  fi

  REASON="pre-compact-$TRIGGER"
  TITLE="Auto-rollover (context compaction, $TRIGGER)"

  if [ ! -f scripts/memory.py ]; then
    echo "scripts/memory.py missing — skipping handover creation"
  elif NEW=$(python3 scripts/memory.py create --title "$TITLE" --reason "$REASON" 2>>"$LOG"); then
    echo "created handover: $NEW"
    if [ -x scripts/notify-slack.sh ]; then
      bash scripts/notify-slack.sh "Auto-rollover" "Pre-compact handover created: $NEW (reason: $REASON)" >/dev/null 2>&1 || true
    fi
  else
    echo "memory.py create failed; continuing anyway"
  fi
} >>"$LOG" 2>&1

# Never block compaction — single exit point so it can never be bypassed.
exit 0
