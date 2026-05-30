#!/usr/bin/env python3
"""Generate the next sequential handover with carry-forward continuity.

Reads the prior handover (highest numbered) and pulls forward:
- Section 0 "Standing instructions" -> new doc's section 0
- Section 7 "Next session" -> new doc's section 3 (open threads)

Also auto-populates:
- Section 4 with currently open tasks from docs/plan.md
- Section 5 with the last 10 git commits
- Section 6 with stale-reference flags (paths/branches no longer present)

The previous handover's `next:` front-matter field is updated to point at
the new file, and its `status` flips to `superseded`.

Usage:
    scripts/handover-new.py [--title "One-line title"] [--session-id session-XXX]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required (pip install --user pyyaml)", file=sys.stderr)
    sys.exit(1)


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import repo_root, handovers_dir, plan_path

REPO_ROOT = repo_root()
HANDOVERS_DIR = handovers_dir()
PLAN_PATH = plan_path()

HANDOVER_RE = re.compile(r"^handover_(\d{3})\.md$")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    return yaml.safe_load(parts[1]) or {}, parts[2]


def list_handovers() -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for p in HANDOVERS_DIR.glob("handover_*.md"):
        m = HANDOVER_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    out.sort()
    return out


def extract_section(body: str, heading_re: str) -> str:
    """Extract content under the first matching heading until the next same-or-higher heading."""
    lines = body.splitlines()
    start: int | None = None
    end = len(lines)
    pat = re.compile(heading_re, re.IGNORECASE)
    origin_level = 0
    for i, line in enumerate(lines):
        if line.startswith("#") and pat.search(line.lstrip("#").strip()):
            start = i + 1
            origin_level = len(line) - len(line.lstrip("#"))
            continue
        if start is not None and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level <= origin_level:
                end = i
                break
    if start is None:
        return ""
    return "\n".join(lines[start:end]).strip()


def open_tasks_snapshot() -> list[dict[str, Any]]:
    if not PLAN_PATH.exists():
        return []
    text = PLAN_PATH.read_text(encoding="utf-8")
    fm, _ = split_frontmatter(text)
    tasks = fm.get("tasks") or []
    return [t for t in tasks if not t.get("passes") and not t.get("blocked")]


def recent_commits(n: int = 10) -> list[dict[str, str]]:
    try:
        res = subprocess.run(
            ["git", "log", f"-{n}", "--pretty=format:%h|%ad|%s", "--date=short"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        commits = []
        for line in res.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"sha": parts[0], "date": parts[1], "subject": parts[2]})
        return commits
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return []


def find_stale_references(prev_text: str) -> list[str]:
    """Detect file paths and short SHAs mentioned in the prior handover that
    no longer exist or no longer resolve."""
    stale: list[str] = []
    # File-path heuristic: tokens that look like paths (contain `/` and a dot)
    path_re = re.compile(r"[`\"]?((?:[a-zA-Z0-9_.-]+/){1,}[a-zA-Z0-9_.-]+\.[a-zA-Z0-9]{1,8})[`\"]?")
    seen: set[str] = set()
    for m in path_re.finditer(prev_text):
        candidate = m.group(1).strip().strip(".,;)")
        if candidate in seen:
            continue
        seen.add(candidate)
        if "/" not in candidate:
            continue
        # Skip URLs and obvious non-paths
        if candidate.startswith(("http", "https", "ftp")):
            continue
        full = REPO_ROOT / candidate
        if not full.exists():
            # Skip references to paths the consumer has explicitly told us
            # to ignore — typically nested submodules or untracked vendored
            # directories. The IRIS_STALE_PATH_IGNORE env var holds a
            # colon-separated list of path prefixes (e.g.
            # "vendor/:third_party/"). Consumers set this to skip their
            # own nested repos without forking the validator.
            ignore_prefixes = [
                p.strip() for p in (os.environ.get("IRIS_STALE_PATH_IGNORE", "") or "").split(":")
                if p.strip()
            ]
            if any(candidate.startswith(prefix) for prefix in ignore_prefixes):
                continue
            stale.append(candidate)
    # SHA heuristic: 7-12 hex chars mentioned in backticks
    sha_re = re.compile(r"`([0-9a-f]{7,12})`")
    for m in sha_re.finditer(prev_text):
        sha = m.group(1)
        try:
            res = subprocess.run(
                ["git", "cat-file", "-e", sha],
                cwd=str(REPO_ROOT),
                capture_output=True,
                timeout=3,
            )
            if res.returncode != 0:
                stale.append(f"sha:{sha}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return sorted(set(stale))[:40]


def main() -> int:
    ap = argparse.ArgumentParser(description="Create next handover with carry-forward.")
    ap.add_argument("--title", default="", help="Session title (one line).")
    ap.add_argument("--session-id", default=None, help="Session id (default: derived from number).")
    ap.add_argument("--dry-run", action="store_true", help="Print without writing.")
    args = ap.parse_args()

    if not HANDOVERS_DIR.exists():
        HANDOVERS_DIR.mkdir(parents=True)

    existing = list_handovers()
    next_num = (existing[-1][0] + 1) if existing else 1
    fname = f"handover_{next_num:03d}.md"
    new_path = HANDOVERS_DIR / fname
    if new_path.exists():
        print(f"ERROR: {fname} already exists", file=sys.stderr)
        return 1

    prev_path = existing[-1][1] if existing else None
    standing = next_session = ""
    stale: list[str] = []
    if prev_path:
        prev_text = prev_path.read_text(encoding="utf-8")
        _, prev_body = split_frontmatter(prev_text)
        standing = extract_section(prev_body, r"(STANDING\s+INSTRUCTIONS|Standing\s+instructions)")
        next_session = extract_section(prev_body, r"(Next\s+session|NEXT\s+SESSION)")
        stale = find_stale_references(prev_body)

    tasks = open_tasks_snapshot()
    commits = recent_commits(10)
    today = date.today().isoformat()

    session_id = args.session_id or f"session-{next_num:03d}"
    title = args.title or "(set title)"
    prev_yaml = f'"{prev_path.name}"' if prev_path else "null"

    standing_block = standing.strip() if standing else "_(no prior standing instructions found)_"
    next_block = next_session.strip() if next_session else "_(no prior \"next session\" section found)_"

    tasks_lines = "\n".join(
        f"- **{t.get('id')}** (P{t.get('priority', '?')}): {t.get('title', '')}" for t in tasks
    ) or "_(no open tasks)_"

    commits_lines = "\n".join(
        f"- `{c['sha']}` {c['date']} — {c['subject']}" for c in commits
    ) or "_(no recent commits)_"

    stale_lines = "\n".join(f"- `{s}`" for s in stale) or "_(none detected)_"

    frontmatter = f"""---
session_id: {session_id}
date: {today}
title: "{title}"
prev: {prev_yaml}
next: null
status: current
tags: []
source: handovers/{fname}
---"""

    body = f"""

# Handover {next_num:03d} — {title} ({today})

Successor to `{prev_path.name if prev_path else '(first)'}`.

## 0. Standing instructions (carried forward)

{standing_block}

## 1. Branch state

| Repo | Branch | HEAD | Origin? |
|------|--------|------|---------|
| _(fill in)_ | | | |

## 2. What changed this session

_(fill in — bullet list of meaningful changes)_

## 3. Open threads carried forward (from prev "Next session")

{next_block}

## 4. Open tasks (snapshot from docs/plan.md at {today})

{tasks_lines}

## 5. Recent commits

{commits_lines}

## 6. Flagged stale references

{stale_lines}

## 7. Next session — start here

_(fill in — be specific: file paths, commands, success criteria)_

## 8. Open questions / decisions pending

_(fill in)_
"""

    final = frontmatter + body

    if args.dry_run:
        print(final)
        print(f"\n--- DRY RUN: would write {new_path} ({len(final)} bytes) ---", file=sys.stderr)
        if prev_path:
            print(f"--- DRY RUN: would update prev '{prev_path.name}' next:{fname} status:superseded ---", file=sys.stderr)
        return 0

    new_path.write_text(final, encoding="utf-8")
    print(f"created: {new_path}", file=sys.stderr)

    if prev_path:
        prev_text = prev_path.read_text(encoding="utf-8")
        prev_fm, prev_body_only = split_frontmatter(prev_text)
        prev_fm["next"] = fname
        prev_fm["status"] = "superseded"
        new_prev = (
            "---\n"
            + yaml.safe_dump(prev_fm, sort_keys=False, allow_unicode=True, default_flow_style=False)
            + "---"
            + prev_body_only
        )
        prev_path.write_text(new_prev, encoding="utf-8")
        print(f"updated: {prev_path.name} (next={fname}, status=superseded)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
