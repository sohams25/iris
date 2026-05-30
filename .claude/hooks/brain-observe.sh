#!/usr/bin/env bash
# UserPromptSubmit (optional) — log the prompt for the second brain to distil.
#
# OFF by default and not wired into settings.json. To enable automatic capture:
#   1. add this as a UserPromptSubmit hook in .claude/settings.json
#   2. set BRAIN_OBSERVE=on in .env
# When off it exits immediately (no python spawned). It only ever appends to the
# gitignored .iris-state/second-brain/prompts.jsonl and never blocks the prompt.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || exit 0

on="${BRAIN_OBSERVE:-}"
if [ -z "$on" ] && [ -f "$ROOT/.env" ]; then
  on="$(sed -n 's/^[[:space:]]*\(export[[:space:]]*\)\?BRAIN_OBSERVE=//p' "$ROOT/.env" 2>/dev/null \
        | tail -1 | tr -d "\"' " | sed 's/[[:space:]]*#.*//')"
fi
[ "$on" = "on" ] || exit 0   # fast path: nothing to do

payload="$(cat 2>/dev/null || true)"
[ -z "$payload" ] && exit 0
dir="$ROOT/.iris-state/second-brain"
mkdir -p "$dir" 2>/dev/null || exit 0
printf '%s' "$payload" | python3 -c '
import json, sys
try:
    p = json.loads(sys.stdin.read() or "{}").get("prompt", "")
except Exception:
    p = ""
if p.strip():
    print(json.dumps({"prompt": p}))
' >> "$dir/prompts.jsonl" 2>/dev/null || true
exit 0
