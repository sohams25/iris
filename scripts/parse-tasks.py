#!/usr/bin/env python3
"""Read/write the YAML task backlog inside docs/plan.md.

The plan file has a YAML front-matter delimited by `---` markers, followed
by free-form markdown. This script preserves the markdown body exactly and
only rewrites the front-matter on update.

Subcommands:
    next     Print the next task to work on as JSON, or empty string if none.
    list     Print all tasks as JSON array.
    mark     Set a key on a task by id.  parse-tasks.py mark T001 passes true
    note     Append a note to a task.    parse-tasks.py note T001 "ran 3x; verify red"
    add      Append a new task.          parse-tasks.py add --id T010 --title "..." [--priority N] [--files a,b,c] [--notes "..."]

Exit codes:
    0  success
    1  IO or parse error
    2  task not found
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML not installed. Run: python3 -m pip install --user pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import plan_path

PLAN_PATH = plan_path()


def load() -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, markdown_body)."""
    if not PLAN_PATH.exists():
        raise SystemExit(f"{PLAN_PATH}: not found")
    text = PLAN_PATH.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SystemExit(f"{PLAN_PATH}: missing YAML front-matter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SystemExit(f"{PLAN_PATH}: malformed front-matter")
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]
    return fm, body


def save(fm: dict[str, Any], body: str) -> None:
    fm_text = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    PLAN_PATH.write_text(f"---\n{fm_text}---{body}", encoding="utf-8")


def next_task() -> dict[str, Any] | None:
    fm, _ = load()
    tasks = fm.get("tasks") or []
    open_tasks = [
        t for t in tasks if not t.get("passes") and not t.get("blocked")
    ]
    if not open_tasks:
        return None
    open_tasks.sort(key=lambda t: (t.get("priority", 999), t.get("id", "")))
    return open_tasks[0]


def find_task(task_id: str) -> tuple[dict[str, Any], str, list[dict[str, Any]], int]:
    fm, body = load()
    tasks = fm.get("tasks") or []
    for i, t in enumerate(tasks):
        if t.get("id") == task_id:
            return fm, body, tasks, i
    raise SystemExit(2)


def parse_value(raw: str) -> Any:
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def cmd_next() -> int:
    t = next_task()
    print(json.dumps(t) if t else "")
    return 0


def cmd_list() -> int:
    fm, _ = load()
    print(json.dumps(fm.get("tasks") or []))
    return 0


def cmd_mark(args: list[str]) -> int:
    if len(args) != 3:
        print("usage: parse-tasks.py mark <id> <key> <value>", file=sys.stderr)
        return 1
    task_id, key, value = args
    fm, body, tasks, i = find_task(task_id)
    tasks[i][key] = parse_value(value)
    fm["tasks"] = tasks
    save(fm, body)
    return 0


def cmd_note(args: list[str]) -> int:
    if len(args) != 2:
        print("usage: parse-tasks.py note <id> <text>", file=sys.stderr)
        return 1
    task_id, text = args
    fm, body, tasks, i = find_task(task_id)
    existing = tasks[i].get("notes") or ""
    sep = "\n" if existing else ""
    tasks[i]["notes"] = f"{existing}{sep}{text}"
    fm["tasks"] = tasks
    save(fm, body)
    return 0


def cmd_add(args: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="parse-tasks.py add")
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--priority", type=int, default=None)
    ap.add_argument("--files", default="")
    ap.add_argument("--notes", default="")
    try:
        ns = ap.parse_args(args)
    except SystemExit:
        return 1
    fm, body = load()
    tasks = list(fm.get("tasks") or [])
    if any(t.get("id") == ns.id for t in tasks):
        print(f"task id already exists: {ns.id}", file=sys.stderr)
        return 1
    priority = ns.priority
    if priority is None:
        priority = max((int(t.get("priority", 0) or 0) for t in tasks), default=0) + 1
    files = [f.strip() for f in ns.files.split(",") if f.strip()] if ns.files else []
    new_task = {
        "id": ns.id,
        "title": ns.title,
        "priority": priority,
        "files": files,
        "passes": False,
        "blocked": False,
        "notes": ns.notes,
    }
    tasks.append(new_task)
    fm["tasks"] = tasks
    save(fm, body)
    print(ns.id)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    sub = argv[1]
    rest = argv[2:]
    handlers = {
        "next": lambda: cmd_next(),
        "list": lambda: cmd_list(),
        "mark": lambda: cmd_mark(rest),
        "note": lambda: cmd_note(rest),
        "add": lambda: cmd_add(rest),
    }
    fn = handlers.get(sub)
    if not fn:
        print(f"unknown subcommand: {sub}", file=sys.stderr)
        return 1
    return fn()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
