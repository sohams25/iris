"""scripts/queue.py — plan-ahead queue drains docs/next.md into the backlog.

The producer (you editing docs/next.md) and the consumer (the /run loop calling
`queue.py drain` between tasks) sync only at the drain. These tests pin the
consumer side: ingest, archive, reset, idempotency, and that comments/blanks
are ignored.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE = REPO_ROOT / "scripts" / "queue.py"
PARSE = REPO_ROOT / "scripts" / "parse-tasks.py"

PLAN_FIXTURE = """\
---
tasks:
  - id: T001
    title: "seed task"
    priority: 1
    files: ["a.py"]
    passes: false
    blocked: false
---

# Backlog
"""


def _project(tmp_path: Path, next_body: str) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text(PLAN_FIXTURE)
    (tmp_path / "docs" / "next.md").write_text(next_body)
    return tmp_path


def _run(tmp_path: Path, script: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(tmp_path), capture_output=True, text=True,
        env={**os.environ, "MEMORY_BACKEND": "markdown"}, timeout=20,
    )


def _tasks(tmp_path: Path) -> list[dict]:
    res = _run(tmp_path, PARSE, "list")
    return json.loads(res.stdout)


def test_drain_ingests_bullets_and_resets(tmp_path):
    _project(tmp_path, "# a comment\n- add rate limiter\n* refactor cache\nT: write tests\n\n")
    res = _run(tmp_path, QUEUE, "drain")
    assert res.returncode == 0, res.stderr
    titles = [t["title"] for t in _tasks(tmp_path)]
    assert titles == ["seed task", "add rate limiter", "refactor cache", "write tests"]
    # next.md reset to the template (first line is the header comment)
    assert (tmp_path / "docs" / "next.md").read_text().startswith("# docs/next.md")
    # exactly one archive file was written
    archive = tmp_path / ".iris-state" / "queue-archive"
    assert archive.is_dir() and len(list(archive.glob("*.md"))) == 1


def test_comments_and_blanks_only_is_empty(tmp_path):
    _project(tmp_path, "# just a comment\n\n#another\n")
    res = _run(tmp_path, QUEUE, "drain")
    assert res.returncode == 0
    assert "queue empty" in res.stdout
    assert [t["id"] for t in _tasks(tmp_path)] == ["T001"]  # nothing added


def test_double_drain_does_not_double_add(tmp_path):
    _project(tmp_path, "- one\n- two\n")
    assert _run(tmp_path, QUEUE, "drain").returncode == 0
    n1 = len(_tasks(tmp_path))
    assert _run(tmp_path, QUEUE, "drain").returncode == 0  # second drain on the reset file
    n2 = len(_tasks(tmp_path))
    assert n1 == n2 == 3  # seed + 2, unchanged


def test_status_does_not_consume(tmp_path):
    _project(tmp_path, "- pending one\n- pending two\n")
    res = _run(tmp_path, QUEUE, "status")
    assert res.returncode == 0
    assert "2 pending" in res.stdout
    assert [t["id"] for t in _tasks(tmp_path)] == ["T001"]  # still not ingested


def test_ids_continue_from_backlog_high_water(tmp_path):
    _project(tmp_path, "- new one\n")
    _run(tmp_path, QUEUE, "drain")
    ids = [t["id"] for t in _tasks(tmp_path)]
    assert ids == ["T001", "T002"]  # next id after the seed's T001


def test_ingest_failure_reports_and_keeps_archive(tmp_path):
    # docs/next.md has items but there's no docs/plan.md, so `add` fails. The
    # drain must report the un-ingested items and keep the claimed archive so
    # nothing is silently lost.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "next.md").write_text("- alpha\n- beta\n")
    res = _run(tmp_path, QUEUE, "drain")
    assert res.returncode == 1
    assert "NOT ingested" in res.stderr
    assert "alpha" in res.stderr and "beta" in res.stderr
    files = list((tmp_path / ".iris-state" / "queue-archive").glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text()
    assert "alpha" in body and "beta" in body
