#!/usr/bin/env python3
"""Plan-ahead queue — drain docs/next.md into the backlog at safe checkpoints.

Jot future tasks into the watched file (docs/next.md, or $NEXT_PATH) while a
/run loop works the current task. The loop calls `queue.py drain` at each task
boundary: it ingests every pending line as a new open backlog task, archives
what it consumed, and resets the file. The in-flight task is never touched —
items you save become available for the NEXT iteration, not the current one.

Subcommands:
    drain    Ingest pending items from docs/next.md into docs/plan.md.
    status   List pending items without consuming them.

Exit codes:
    0  success (including "queue empty")
    1  IO / ingest error
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import next_path, repo_root, state_dir

PARSE_TASKS = Path(__file__).resolve().parent / "parse-tasks.py"

TEMPLATE = """\
# docs/next.md — plan-ahead queue.
#
# Jot future tasks here, one per line, while a /run loop works the current
# task. The loop drains this file into docs/plan.md at each task boundary and
# resets it. Lines starting with '#' are ignored; a leading '-', '*' or 'T:'
# is optional.
#
# Examples:
# - add a rate limiter to the public API
# - refactor the cache layer for clarity
"""


def _items(text: str) -> list[str]:
    """Pending task lines: non-blank, non-comment; leading bullet/T: stripped."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line[:1] in ("-", "*"):
            line = line[1:].lstrip()      # bullet, with or without a space
        elif line.startswith("T:"):
            line = line[2:].lstrip()
        if line:
            out.append(line)
    return out


def _next_ids(n: int) -> list[str]:
    """The next n unused T### ids, based on the current backlog."""
    res = subprocess.run(
        ["python3", str(PARSE_TASKS), "list"],
        cwd=str(repo_root()), capture_output=True, text=True,
    )
    highest = 0
    if res.returncode == 0 and res.stdout.strip():
        try:
            for t in json.loads(res.stdout):
                tid = str(t.get("id", ""))
                if tid.startswith("T") and tid[1:].isdigit():
                    highest = max(highest, int(tid[1:]))
        except json.JSONDecodeError:
            pass
    return [f"T{highest + i:03d}" for i in range(1, n + 1)]


def cmd_status() -> int:
    np = next_path()
    items = _items(np.read_text(encoding="utf-8")) if np.exists() else []
    if not items:
        print("queue empty")
        return 0
    print(f"{len(items)} pending:")
    for it in items:
        print(f"  - {it}")
    return 0


def cmd_drain() -> int:
    np = next_path()
    if not np.exists():
        np.parent.mkdir(parents=True, exist_ok=True)
        np.write_text(TEMPLATE, encoding="utf-8")
        print("queue empty")
        return 0

    # Atomic claim: rename the file out of the way so a concurrent editor save
    # lands on a fresh file and is never lost. The claimed copy is an atomic
    # snapshot we parse at leisure.
    archive_dir = state_dir() / "queue-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    claimed = archive_dir / f"{stamp}.md"
    np.rename(claimed)
    items = _items(claimed.read_text(encoding="utf-8"))

    ingested: list[str] = []
    items_list = list(items)
    for idx, (tid, title) in enumerate(zip(_next_ids(len(items_list)), items_list)):
        res = subprocess.run(
            ["python3", str(PARSE_TASKS), "add", "--id", tid, "--title", title],
            cwd=str(repo_root()), capture_output=True, text=True,
        )
        if res.returncode != 0:
            print(f"failed to ingest {tid} ({title!r}): {res.stderr.strip()}", file=sys.stderr)
            remaining = items_list[idx:]
            print(f"{len(remaining)} item(s) NOT ingested — recover from {claimed} "
                  f"or re-add to docs/next.md:", file=sys.stderr)
            for t in remaining:
                print(f"  - {t}", file=sys.stderr)
            return 1
        ingested.append(tid)

    # Restore the template only if a concurrent editor hasn't already recreated
    # the file with new content — never clobber an unsaved-then-saved edit.
    if not np.exists():
        np.write_text(TEMPLATE, encoding="utf-8")

    if not ingested:
        try:
            claimed.unlink()  # nothing actionable — don't litter the archive
        except OSError:
            pass
        print("queue empty")
        return 0
    print(f"ingested {len(ingested)} task(s): {', '.join(ingested)}")
    return 0


def main(argv: list[str]) -> int:
    sub = argv[1] if len(argv) > 1 else ""
    if sub == "drain":
        return cmd_drain()
    if sub == "status":
        return cmd_status()
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
