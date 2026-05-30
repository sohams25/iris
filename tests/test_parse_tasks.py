"""scripts/parse-tasks.py — list / next on a synthetic plan.md."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PARSE = REPO_ROOT / "scripts" / "parse-tasks.py"

SAMPLE = """---
tasks:
  - id: T001
    title: "first"
    status: open
    priority: 1
    files: ["a.py"]
  - id: T002
    title: "second"
    status: blocked
    blocked_by: T001
    priority: 2
    files: ["b.py"]
  - id: T003
    title: "third"
    status: passed
    priority: 3
    files: ["c.py"]
---
"""


def test_parse_tasks_list(tmp_path):
    plan = tmp_path / "docs" / "plan.md"
    plan.parent.mkdir()
    plan.write_text(SAMPLE)
    res = subprocess.run(
        [sys.executable, str(PARSE), "list"],
        cwd=str(tmp_path),
        env={"PLAN_PATH": "docs/plan.md", "PATH": __import__("os").environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    ids = [t["id"] for t in data]
    assert "T001" in ids
    assert "T002" in ids
