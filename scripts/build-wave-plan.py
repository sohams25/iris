#!/usr/bin/env python3
"""Build a wave execution plan from docs/plan.md for the /swarm command.

A "wave" is a set of tasks that can execute concurrently because none of
them share files. The output is a JSON document the orchestrator reads to
decide what to launch in parallel and in what order.

Algorithm:
    1. Load all open tasks (passes=False, blocked=False), sorted by priority.
    2. Greedily assign each task to the earliest wave whose committed file
       set does not intersect the task's file set.
    3. Tasks with empty files[] are conservative: each occupies its own wave.
    4. Tasks using globs (containing '*' or '?') are also conservative —
       treat them as exclusive to their wave (overlap detection is not safe
       to evaluate statically against unknown future files).

Output schema (printed to stdout as JSON):
    {
        "waves": [
            {"id": 1, "tasks": [{...task...}, ...]},
            ...
        ],
        "stats": {"total_tasks": N, "wave_count": W}
    }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. python3 -m pip install --user pyyaml", file=sys.stderr)
    sys.exit(1)


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _iris_paths import plan_path

PLAN_PATH = plan_path()


def load_tasks() -> list[dict[str, Any]]:
    if not PLAN_PATH.exists():
        raise SystemExit(f"{PLAN_PATH}: not found")
    text = PLAN_PATH.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SystemExit(f"{PLAN_PATH}: missing or malformed YAML front-matter")
    fm = yaml.safe_load(parts[1]) or {}
    tasks = fm.get("tasks") or []
    return [t for t in tasks if not t.get("passes") and not t.get("blocked")]


def is_glob(path: str) -> bool:
    return any(c in path for c in "*?[")


def is_exclusive(task: dict[str, Any]) -> bool:
    """A task that should run alone in its wave."""
    files = task.get("files") or []
    if not files:
        return True
    return any(is_glob(f) for f in files)


def build_waves(tasks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    tasks_sorted = sorted(
        tasks, key=lambda t: (t.get("priority", 999), t.get("id", ""))
    )
    waves: list[list[dict[str, Any]]] = []
    wave_files: list[set[str]] = []
    wave_exclusive: list[bool] = []

    for task in tasks_sorted:
        task_files = set(task.get("files") or [])
        exclusive = is_exclusive(task)
        placed = False
        for i, (used, excl) in enumerate(zip(wave_files, wave_exclusive)):
            if excl or exclusive:
                continue
            if task_files & used:
                continue
            waves[i].append(task)
            wave_files[i] |= task_files
            placed = True
            break
        if not placed:
            waves.append([task])
            wave_files.append(task_files)
            wave_exclusive.append(exclusive)

    return waves


def main() -> int:
    tasks = load_tasks()
    waves = build_waves(tasks)
    out = {
        "waves": [
            {"id": i + 1, "tasks": w} for i, w in enumerate(waves)
        ],
        "stats": {"total_tasks": len(tasks), "wave_count": len(waves)},
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
