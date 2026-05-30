"""scripts/doctor.py — runs to completion, JSON shape is well-formed."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCTOR = REPO_ROOT / "scripts" / "doctor.py"


def test_doctor_json_well_formed():
    env = {**os.environ, "MEMORY_BACKEND": "markdown", "PROJECTS_DIR": "Tasks"}
    res = subprocess.run(
        [sys.executable, str(DOCTOR), "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert len(data) >= 10
    for check in data:
        assert "name" in check
        assert "ok" in check
        assert "detail" in check


def test_doctor_human_output_has_summary():
    env = {**os.environ, "MEMORY_BACKEND": "markdown"}
    res = subprocess.run(
        [sys.executable, str(DOCTOR)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert "doctor —" in res.stdout
    assert "checks pass" in res.stdout
