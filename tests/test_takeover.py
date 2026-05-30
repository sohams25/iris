"""scripts/takeover.py — the autonomous-takeover gate (toggle, budgets, kill-switch).

The self-prompting loop itself is model-driven (the /takeover command); these
tests pin the deterministic gate it polls, plus an end-to-end cycle that wires
the brain, the gate, and the backlog together.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TAKEOVER = REPO_ROOT / "scripts" / "takeover.py"


def _to(root: Path, *args) -> subprocess.CompletedProcess:
    env = {**os.environ, "IRIS_ROOT": str(root)}
    return subprocess.run([sys.executable, str(TAKEOVER), *args],
                          capture_output=True, text=True, env=env, timeout=10)


def _status(root: Path) -> dict:
    return json.loads(_to(root, "status", "--json").stdout)


def test_on_status_off(tmp_path):
    assert _to(tmp_path, "on").returncode == 0
    assert _status(tmp_path)["mode"] == "on"
    _to(tmp_path, "off")
    assert _status(tmp_path)["mode"] == "off"


def test_step_continues_then_kill_switch(tmp_path):
    _to(tmp_path, "on")
    r = _to(tmp_path, "step")
    assert r.returncode == 0 and "continue" in r.stdout
    _to(tmp_path, "off", "--reason", "user")          # kill-switch
    r = _to(tmp_path, "step")
    assert r.returncode == 3 and "killed" in r.stdout   # loop must stop


def test_cycle_budget_stops(tmp_path):
    _to(tmp_path, "on", "--budget-cycles", "2")
    assert _to(tmp_path, "step").returncode == 0       # cycle 1
    assert _to(tmp_path, "step").returncode == 0       # cycle 2
    r = _to(tmp_path, "step")                            # cycle 3 > budget
    assert r.returncode == 3 and "cycle budget" in r.stdout


def test_stagnation_stops_after_three(tmp_path):
    _to(tmp_path, "on")
    assert _to(tmp_path, "step", "--progress", "0").returncode == 0
    assert _to(tmp_path, "step", "--progress", "0").returncode == 0
    r = _to(tmp_path, "step", "--progress", "0")
    assert r.returncode == 3 and "stagnation" in r.stdout


def test_progress_resets_stagnation(tmp_path):
    _to(tmp_path, "on")
    _to(tmp_path, "step", "--progress", "0")
    _to(tmp_path, "step", "--progress", "1")           # progress resets the counter
    assert _to(tmp_path, "step", "--progress", "0").returncode == 0
    assert _to(tmp_path, "step", "--progress", "0").returncode == 0  # only 2 in a row now


def test_bare_steps_count_as_stagnation(tmp_path):
    # a loop that forgets --progress can't bypass stagnation: bare steps count 0
    _to(tmp_path, "on")
    assert _to(tmp_path, "step").returncode == 0
    assert _to(tmp_path, "step").returncode == 0
    assert _to(tmp_path, "step").returncode == 3   # 3rd zero-progress -> stop


def test_log_writes_audit(tmp_path):
    _to(tmp_path, "on")
    _to(tmp_path, "log", "decided to refactor the cache")
    logf = tmp_path / ".iris-state" / "takeover" / "log.jsonl"
    assert logf.exists() and "refactor the cache" in logf.read_text()


def test_integration_one_cycle(tmp_path):
    """observe -> simulate (decide) -> add task (execute) -> reward (learn) -> gate."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text("---\ntasks: []\n---\n")
    env = {**os.environ, "IRIS_ROOT": str(tmp_path),
           "IRIS_HOME": str(tmp_path / "home"), "BRAIN_SEED": "7"}

    def run(script, *a):
        return subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), *a],
                              cwd=str(tmp_path), capture_output=True, text=True, env=env, timeout=20)

    assert run("takeover.py", "on").returncode == 0
    run("brain.py", "observe", "--domain", "objective", "--pattern", "ship the smallest thing first")
    sim = json.loads(run("brain.py", "simulate", "--domain", "objective", "--json").stdout)
    assert sim["id"] == "ship-the-smallest-thing-first"            # the brain fed the decision
    assert run("parse-tasks.py", "add", "--id", "T001", "--title", "smallest thing").returncode == 0
    assert run("brain.py", "reward", "ship-the-smallest-thing-first", "1.0").returncode == 0  # learned
    assert run("takeover.py", "step").returncode == 0             # loop continues
