"""scripts/memory.py — markdown backend round-trip."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MEMORY = REPO_ROOT / "scripts" / "memory.py"


def memory(tmp_path: Path, *args, env_extra=None) -> subprocess.CompletedProcess:
    """Run scripts/memory.py with MEMORY_BACKEND=markdown rooted in tmp_path."""
    env = {**os.environ, "MEMORY_BACKEND": "markdown"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(MEMORY), *args],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_list_on_empty_repo_returns_empty(tmp_path):
    res = memory(tmp_path, "list", "--json")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == []


def test_create_and_list_round_trip(tmp_path):
    res = memory(tmp_path, "create", "--title", "test handover", "--reason", "manual")
    assert res.returncode == 0, res.stderr
    hid = res.stdout.strip()
    assert hid.endswith(".md") or hid.startswith("handover_")

    res = memory(tmp_path, "list", "--json")
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert len(data) == 1
    assert data[0]["id"] == hid


def test_validate_clean_on_fresh_repo(tmp_path):
    res = memory(tmp_path, "validate")
    assert res.returncode == 0, res.stderr
    assert "no issues" in res.stdout.lower() or "0 issues" in res.stdout.lower() or "checked" in res.stdout.lower()
