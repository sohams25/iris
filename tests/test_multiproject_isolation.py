"""Multiple iris projects stay isolated — answers 'can I work on several at once?'

- markdown backend: two distinct $IRIS_ROOT projects keep separate handovers/.
- obsidian backend: two $IRIS_PROJECT namespaces share one vault without
  mixing their handover chains.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MEMORY = REPO_ROOT / "scripts" / "memory.py"


def _run(args, *, cwd, env_extra) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_extra}
    return subprocess.run(
        [sys.executable, str(MEMORY), *args],
        cwd=str(cwd), capture_output=True, text=True, env=env, timeout=20,
    )


def test_markdown_two_projects_isolated(tmp_path):
    """Two $IRIS_ROOT projects each get their own handovers/ — no cross-talk."""
    a = tmp_path / "proj_a"
    a.mkdir()
    b = tmp_path / "proj_b"
    b.mkdir()
    base = {"MEMORY_BACKEND": "markdown"}

    # cwd is deliberately neither root — $IRIS_ROOT must win.
    ra = _run(["create", "--title", "alpha work", "--reason", "manual"],
              cwd=tmp_path, env_extra={**base, "IRIS_ROOT": str(a)})
    assert ra.returncode == 0, ra.stderr
    rb = _run(["create", "--title", "beta work", "--reason", "manual"],
              cwd=tmp_path, env_extra={**base, "IRIS_ROOT": str(b)})
    assert rb.returncode == 0, rb.stderr

    assert len(list((a / "handovers").glob("handover_*.md"))) == 1
    assert len(list((b / "handovers").glob("handover_*.md"))) == 1

    la = _run(["list", "--json"], cwd=tmp_path, env_extra={**base, "IRIS_ROOT": str(a)})
    lb = _run(["list", "--json"], cwd=tmp_path, env_extra={**base, "IRIS_ROOT": str(b)})
    da = json.loads(la.stdout)
    db = json.loads(lb.stdout)
    assert len(da) == 1 and da[0]["title"] == "alpha work"
    assert len(db) == 1 and db[0]["title"] == "beta work"


def test_obsidian_two_projects_namespaced(tmp_path):
    """Two $IRIS_PROJECT namespaces share one vault, isolated under <project>/."""
    vault = tmp_path / "vault"
    vault.mkdir()
    base = {"MEMORY_BACKEND": "obsidian", "OBSIDIAN_VAULT": str(vault)}

    ra = _run(["create", "--title", "alpha", "--reason", "manual"],
              cwd=tmp_path, env_extra={**base, "IRIS_PROJECT": "alpha"})
    assert ra.returncode == 0, ra.stderr
    rb = _run(["create", "--title", "beta", "--reason", "manual"],
              cwd=tmp_path, env_extra={**base, "IRIS_PROJECT": "beta"})
    assert rb.returncode == 0, rb.stderr

    handovers = vault / "work" / "handovers"
    assert list((handovers / "alpha").glob("*.md")), "alpha namespace empty"
    assert list((handovers / "beta").glob("*.md")), "beta namespace empty"

    la = _run(["list", "--json"], cwd=tmp_path, env_extra={**base, "IRIS_PROJECT": "alpha"})
    da = json.loads(la.stdout)
    assert len(da) == 1 and da[0]["title"] == "alpha"
