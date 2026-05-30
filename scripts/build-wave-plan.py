#!/usr/bin/env python3
"""Build a wave execution plan from docs/plan.md for /run's router (--decide) and the swarm skill.

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

import argparse
import json
import os
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


def wave_ceiling() -> int:
    """Auto-derived max agents per wave. The work decides the natural
    parallelism (the size of a file-disjoint wave); this ceiling only guards
    against runaway fan-out and scales with the machine. No manual config."""
    return max(2, min((os.cpu_count() or 4) - 1, 8))


def cap_waves(waves: list[list[dict[str, Any]]], width: int) -> list[list[dict[str, Any]]]:
    """Split any wave wider than `width` into width-sized sub-waves. Tasks in a
    wave are already file-disjoint, so any subset is a valid parallel batch."""
    capped: list[list[dict[str, Any]]] = []
    for w in waves:
        for i in range(0, len(w), width):
            capped.append(w[i:i + width])
    return capped


def decide(waves: list[list[dict[str, Any]]], total: int, width: int) -> dict[str, str]:
    """Recommend serial vs parallel from the (already ceiling-capped) waves."""
    max_wave = max((len(w) for w in waves), default=0)
    if total <= 1:
        return {"mode": "serial", "reason": f"{total} open task(s) — nothing to parallelize"}
    if max_wave >= 2:
        return {"mode": "parallel", "reason": (
            f"{total} open tasks include a file-disjoint wave of {max_wave} "
            f"(auto ceiling {width}) — run in parallel waves")}
    return {"mode": "serial", "reason": "every task shares files or is exclusive — no safe parallel wave"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="build-wave-plan.py")
    ap.add_argument("--decide", action="store_true",
                    help="emit a serial/parallel routing decision, not just the waves")
    args = ap.parse_args(argv)

    width = wave_ceiling()
    tasks = load_tasks()
    waves = cap_waves(build_waves(tasks), width)
    wave_objs = [{"id": i + 1, "tasks": w} for i, w in enumerate(waves)]
    stats = {
        "total_tasks": len(tasks),
        "wave_count": len(waves),
        "max_wave_size": max((len(w) for w in waves), default=0),
    }
    if args.decide:
        out = {**decide(waves, len(tasks), width), "width": width, "stats": stats, "waves": wave_objs}
    else:
        out = {"waves": wave_objs, "stats": stats}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
