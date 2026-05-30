#!/usr/bin/env bash
# PreToolUse(Bash) — block git commit / git tag invocations whose message
# body carries an AI-generated signature.
#
# Reads the tool call as JSON on stdin: {"tool_input":{"command":"..."}}.
# When the command is a git commit/tag/rebase with an inline message (-m
# / -F / --message= / --file=), the *message text* is extracted and
# inspected. Other commands and editor-path invocations pass through.
#
# Exit codes:
#   0 — allow (no match, or not a git-commit command)
#   2 — block (Claude sees the stderr block and refuses the tool call)
#
# Designed to be plugin-portable: relies only on python3 stdlib.
set -euo pipefail

payload="$(cat || true)"
[ -z "$payload" ] && exit 0

# All the parsing — JSON unwrap, shell-token split, -m / -F argument
# extraction, and pattern matching — lives in one python block. Bash is
# too brittle for shell-quoting heuristics, and the previous regex-on-
# whole-command approach false-positives on Bash invocations that
# legitimately pass the forbidden strings as fixtures (e.g. this hook's
# own test suite).
result="$(python3 - <<'PY' "$payload"
import json
import re
import shlex
import sys

raw = sys.argv[1]
try:
    payload = json.loads(raw)
except Exception:
    # Malformed payload — fail open. We do not want hook errors to be
    # mistaken for a block, which would silently break every Bash call.
    print("ALLOW")
    sys.exit(0)

tool_name = payload.get("tool_name") or payload.get("tool") or ""
if tool_name != "Bash":
    print("ALLOW")
    sys.exit(0)

command = (payload.get("tool_input") or {}).get("command") or ""
if not command:
    print("ALLOW")
    sys.exit(0)

# Only inspect git commit / git tag / git rebase invocations.
# A loose word-boundary test is enough; we'll re-validate when we
# tokenise below.
if not re.search(r"\bgit\s+(commit|tag|rebase)\b", command):
    print("ALLOW")
    sys.exit(0)

# Tokenise via shlex. The Bash command may legitimately use here-docs
# (<<'EOF' ... EOF) or pipes; shlex handles the common -m "..." and
# -F file forms cleanly. If shlex fails (unbalanced quotes from a
# heredoc, for instance), fall back to a permissive regex pull.
inline_bodies: list[str] = []
file_paths: list[str] = []

try:
    tokens = shlex.split(command, posix=True)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-m", "--message") and i + 1 < len(tokens):
            inline_bodies.append(tokens[i + 1])
            i += 2
            continue
        if t.startswith("--message="):
            inline_bodies.append(t[len("--message="):])
            i += 1
            continue
        if t in ("-F", "--file") and i + 1 < len(tokens):
            file_paths.append(tokens[i + 1])
            i += 2
            continue
        if t.startswith("--file="):
            file_paths.append(t[len("--file="):])
            i += 1
            continue
        i += 1
except ValueError:
    # Quote imbalance — pull -m arguments with a tolerant regex instead.
    for m in re.finditer(r"-m\s+(['\"])(.*?)\1", command, flags=re.DOTALL):
        inline_bodies.append(m.group(2))
    for m in re.finditer(r"--message=(['\"])(.*?)\1", command, flags=re.DOTALL):
        inline_bodies.append(m.group(2))

# If no -m / -F was used at all, the message comes from $EDITOR — we
# cannot see it and will not block it.
if not inline_bodies and not file_paths:
    print("ALLOW")
    sys.exit(0)

# Read any -F files we can. Stat before opening so we never block on a
# FIFO / device, and never read a directory by accident. `-F -` (stdin
# pipe) cannot be re-read here — that path silently falls through to
# fail-open, same as the editor case.
import os as _os
import stat as _stat
for path in file_paths:
    if path in ("-", ""):
        continue
    try:
        st = _os.stat(path)
    except OSError:
        # File may not exist yet (e.g. message file built later in the
        # same command chain). Skip silently — fail open.
        continue
    if not _stat.S_ISREG(st.st_mode):
        # Pipes, sockets, devices, directories — refuse to read. A
        # FIFO with no writer would otherwise block the hook (and the
        # entire Bash tool call) forever.
        continue
    try:
        inline_bodies.append(open(path, "r", encoding="utf-8").read())
    except OSError:
        continue

# Forbidden markers. Lower-cased substring match; the message is also
# lower-cased before matching. Keep these tight to the structural
# signatures Claude Code emits — prose adjectives like "comprehensive"
# are not in scope (the commit-style skill handles voice).
FORBIDDEN = [
    "🤖 generated with",
    "generated with [claude code]",
    "generated with claude code",
    "co-authored-by: claude",
    "co-authored-by: noreply@anthropic",
    "co-authored-by: <noreply@anthropic",
    "<noreply@anthropic.com>",
    "authored by ai",
    "made with claude code",
    "created with claude code",
]

violations: list[str] = []
for body in inline_bodies:
    low = body.lower()
    for marker in FORBIDDEN:
        if marker in low and marker not in violations:
            violations.append(marker)

if not violations:
    print("ALLOW")
    sys.exit(0)

print("BLOCK")
for v in violations:
    print(f"  - {v}")
PY
)" || true

# First line is the verdict; remaining lines are the violation list.
verdict="$(printf '%s\n' "$result" | head -1)"
violations_block="$(printf '%s\n' "$result" | tail -n +2)"

if [ "$verdict" = "BLOCK" ]; then
    cat >&2 <<EOF
[block-ai-commit-trailers] Refusing this git commit — the message body
contains an AI-generated signature. The project's commit-style skill
forbids these footers. Remove the offending lines and retry.

Matched forbidden patterns (inside -m / -F message only):
$violations_block

Reference: .claude/skills/commit-style/SKILL.md

If the user has explicitly asked for AI attribution in writing, override
by editing this hook or running the commit with the hook disabled.
EOF
    exit 2
fi

exit 0
