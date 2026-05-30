"""scripts/brain.py — the second brain's RL + continual-learning machinery.

Every assertion is on the deterministic policy (Claude is the reasoner; this is
the reward/memory). RNG is seeded via $BRAIN_SEED so replay sampling is stable.
$IRIS_HOME is redirected into tmp so the real ~/.iris is never touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAIN = REPO_ROOT / "scripts" / "brain.py"


def _brain(root: Path, *args, home: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "IRIS_ROOT": str(root),
           "IRIS_HOME": str(home or root / "_home"), "BRAIN_SEED": "7"}
    return subprocess.run([sys.executable, str(BRAIN), *args],
                          capture_output=True, text=True, env=env, timeout=20)


def _insts(root: Path, home: Path | None = None) -> dict[str, dict]:
    r = _brain(root, "status", "--json", home=home)
    return {i["id"]: i for i in json.loads(r.stdout)["project"]}


def test_reward_raises_confidence(tmp_path):
    _brain(tmp_path, "observe", "--domain", "d", "--pattern", "p one")
    c0 = _insts(tmp_path)["p-one"]["confidence"]
    for _ in range(4):
        _brain(tmp_path, "reward", "p-one", "1.0")
    assert _insts(tmp_path)["p-one"]["confidence"] > c0


def test_negative_reward_lowers_confidence(tmp_path):
    _brain(tmp_path, "observe", "--domain", "d", "--pattern", "p two")
    for _ in range(3):
        _brain(tmp_path, "reward", "p-two", "1.0")
    hi = _insts(tmp_path)["p-two"]["confidence"]
    _brain(tmp_path, "reward", "p-two", "-1.0")
    assert _insts(tmp_path)["p-two"]["confidence"] < hi


def test_consolidation_reduces_plasticity(tmp_path):
    _brain(tmp_path, "observe", "--domain", "d", "--pattern", "p three")
    p0 = _insts(tmp_path)["p-three"]["plasticity"]
    for _ in range(8):
        _brain(tmp_path, "reward", "p-three", "1.0")
    assert _insts(tmp_path)["p-three"]["plasticity"] < p0  # more evidence -> consolidated


def test_decay_fades_toward_floor_never_below(tmp_path):
    _brain(tmp_path, "observe", "--domain", "d", "--pattern", "p four")
    for _ in range(40):
        _brain(tmp_path, "decay")
    c = _insts(tmp_path)["p-four"]["confidence"]
    assert 0.10 <= c < 0.20   # asymptotes to the floor (0.10), never below


def test_simulate_returns_highest_confidence(tmp_path):
    _brain(tmp_path, "observe", "--domain", "ui", "--pattern", "dark theme")
    _brain(tmp_path, "observe", "--domain", "ui", "--pattern", "light theme")
    for _ in range(4):
        _brain(tmp_path, "reward", "light-theme", "1.0")
    top = json.loads(_brain(tmp_path, "simulate", "--domain", "ui", "--json").stdout)
    assert top["id"] == "light-theme"


def test_promotion_across_two_projects(tmp_path):
    home = tmp_path / "home"
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for p in (a, b, c):
        p.mkdir()
    _brain(a, "observe", "--domain", "d", "--pattern", "shared pref", home=home)
    # one project so far -> not yet promoted (status shows promoted-only globals)
    assert json.loads(_brain(a, "status", "--json", home=home).stdout)["global"] == []
    _brain(b, "observe", "--domain", "d", "--pattern", "shared pref", home=home)
    # seen in two projects -> promoted, and visible from an unrelated third project
    sim = json.loads(_brain(c, "simulate", "--domain", "d", "--json", home=home).stdout)
    assert sim.get("id") == "shared-pref"
    assert sim.get("scope") == "global"


def test_confidence_never_below_floor(tmp_path):
    # even a relentlessly punished instinct bottoms out at the floor, never below
    # (replay and decay share the same floor — the v0.2 invariant fix).
    _brain(tmp_path, "observe", "--domain", "d", "--pattern", "p floor")
    for _ in range(15):
        _brain(tmp_path, "reward", "p-floor", "-1.0")
    for _ in range(10):
        _brain(tmp_path, "decay")
    assert _insts(tmp_path)["p-floor"]["confidence"] >= 0.10


def test_no_catastrophic_forgetting(tmp_path):
    # establish a strong, consolidated anchor
    _brain(tmp_path, "observe", "--domain", "d", "--pattern", "old anchor")
    for _ in range(12):
        _brain(tmp_path, "reward", "old-anchor", "1.0")
    assert _insts(tmp_path)["old-anchor"]["confidence"] > 0.8

    # learn a brand-new pattern hard, under sustained decay pressure
    _brain(tmp_path, "observe", "--domain", "d", "--pattern", "new thing")
    for _ in range(20):
        _brain(tmp_path, "reward", "new-thing", "1.0")
        _brain(tmp_path, "decay")

    after = _insts(tmp_path)
    assert after["new-thing"]["confidence"] > 0.6     # the new pattern was learned
    assert after["old-anchor"]["confidence"] > 0.55   # the anchor was NOT wiped out
