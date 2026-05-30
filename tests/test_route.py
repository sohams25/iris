"""scripts/build-wave-plan.py --decide — auto serial/parallel routing.

`/run` no longer asks you to pick /run vs /swarm; it routes itself off these
decisions. Width is auto-derived (machine-bounded ceiling, never a manual
knob), so the cap tests assert observable behavior rather than a fixed number.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WAVE = REPO_ROOT / "scripts" / "build-wave-plan.py"


def _plan(tmp_path: Path, tasks_yaml: str) -> None:
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "plan.md").write_text(f"---\ntasks:\n{tasks_yaml}---\n")


def _decide(tmp_path: Path) -> dict:
    res = subprocess.run(
        [sys.executable, str(WAVE), "--decide"],
        cwd=str(tmp_path), capture_output=True, text=True,
        env={**os.environ, "PLAN_PATH": "docs/plan.md"}, timeout=10,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _task(i: int, files: list[str]) -> str:
    fl = ", ".join(f'"{f}"' for f in files)
    return (f'  - id: T{i:03d}\n    title: "t{i}"\n    priority: {i}\n'
            f'    files: [{fl}]\n    passes: false\n    blocked: false\n')


def test_single_task_is_serial(tmp_path):
    _plan(tmp_path, _task(1, ["a.py"]))
    assert _decide(tmp_path)["mode"] == "serial"


def test_disjoint_tasks_go_parallel(tmp_path):
    _plan(tmp_path, _task(1, ["a.py"]) + _task(2, ["b.py"]) + _task(3, ["c.py"]))
    d = _decide(tmp_path)
    assert d["mode"] == "parallel"
    assert d["stats"]["max_wave_size"] >= 2


def test_file_sharing_tasks_are_serial(tmp_path):
    # all three touch shared.py → no two can share a wave → max wave size 1
    _plan(tmp_path, _task(1, ["shared.py"]) + _task(2, ["shared.py"]) + _task(3, ["shared.py"]))
    d = _decide(tmp_path)
    assert d["mode"] == "serial"
    assert d["stats"]["max_wave_size"] == 1


def test_empty_files_are_exclusive_serial(tmp_path):
    _plan(tmp_path, _task(1, []) + _task(2, []))
    d = _decide(tmp_path)
    assert d["mode"] == "serial"  # empty files[] → each task is exclusive


def test_width_ceiling_splits_large_disjoint_wave(tmp_path):
    # 25 fully-disjoint tasks must split into multiple width-capped waves.
    yaml = "".join(_task(i, [f"f{i}.py"]) for i in range(1, 26))
    _plan(tmp_path, yaml)
    d = _decide(tmp_path)
    assert d["mode"] == "parallel"
    mw = d["stats"]["max_wave_size"]
    assert 2 <= mw <= 8  # auto ceiling is bounded at 8 regardless of machine
    assert d["stats"]["wave_count"] == math.ceil(25 / mw)
    assert d["width"] == mw
