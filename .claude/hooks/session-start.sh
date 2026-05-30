#!/usr/bin/env bash
# SessionStart hook — load current handover + a tiny project hint into the session.
#
# Output goes to stdout; Claude Code injects it as additional session-start context.
# This hook MUST always exit 0. A broken hook should produce a notice, not a crash.
set -u  # catch undefined vars; rely on || true guards (no pipelines so pipefail is moot)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 0

# Tolerate missing scripts/memory.py during migration.
if [ ! -f scripts/memory.py ]; then
  echo "## iris context"
  echo ""
  echo "_scripts/memory.py is missing — run setup.sh to install iris._"
  exit 0
fi

CURRENT=$(python3 scripts/memory.py current --id-only 2>/dev/null || true)

if [ -z "$CURRENT" ]; then
  echo "## iris context"
  echo ""
  echo "_No current handover found. Use \`/rollover\` to create one, or \`/backlog\` to see work._"
  exit 0
fi

echo "## iris context — current handover: \`$CURRENT\`"
echo ""
echo "The SessionStart hook has loaded the current handover. Treat it as the source of truth for standing instructions, open threads, and decisions in flight."
echo ""
echo "<handover id=\"$CURRENT\">"
python3 scripts/memory.py current 2>/dev/null || echo "_(failed to read handover body)_"
echo "</handover>"
echo ""
echo "Use \`/status\` for a one-screen snapshot. Use \`/run\` to start working the backlog. Use \`/swarm\` to fan out."

exit 0
