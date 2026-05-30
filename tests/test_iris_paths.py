"""scripts/_iris_paths.py — shared path resolution.

The helper resolves "consumer root" to $IRIS_ROOT (explicit override) else the
current working directory, and derives every other path from it. Every iris
script imports from here so they all agree on where the consumer's files live
(never iris's own checkout). These tests pin that contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import _iris_paths  # noqa: E402  (path inserted above so the sibling import resolves)


def test_repo_root_honors_iris_root(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    assert _iris_paths.repo_root() == tmp_path.resolve()


def test_repo_root_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("IRIS_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert _iris_paths.repo_root() == tmp_path.resolve()


def test_iris_root_blank_is_treated_as_unset(tmp_path, monkeypatch):
    # An empty/whitespace IRIS_ROOT must not win over cwd.
    monkeypatch.setenv("IRIS_ROOT", "   ")
    monkeypatch.chdir(tmp_path)
    assert _iris_paths.repo_root() == tmp_path.resolve()


def test_derived_dirs_are_repo_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    root = tmp_path.resolve()
    assert _iris_paths.handovers_dir() == root / "handovers"
    assert _iris_paths.state_dir() == root / ".iris-state"
    assert _iris_paths.env_file() == root / ".env"


def test_plan_path_default_is_repo_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    monkeypatch.delenv("PLAN_PATH", raising=False)
    assert _iris_paths.plan_path() == tmp_path.resolve() / "docs" / "plan.md"


def test_plan_path_honors_relative_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    monkeypatch.setenv("PLAN_PATH", "backlog/tasks.md")
    assert _iris_paths.plan_path() == tmp_path.resolve() / "backlog" / "tasks.md"


def test_plan_path_honors_absolute_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    abs_plan = tmp_path / "elsewhere" / "p.md"
    monkeypatch.setenv("PLAN_PATH", str(abs_plan))
    assert _iris_paths.plan_path() == abs_plan


def test_env_value_handles_export_and_inline_comments(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    for k in ("PATHY", "WIDGET", "QUOTED"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / ".env").write_text(
        "export PATHY=docs/q.md   # trailing comment\n"
        "WIDGET=7\n"
        'QUOTED="a # b"\n'
    )
    assert _iris_paths.env_value("PATHY") == "docs/q.md"   # export + comment stripped
    assert _iris_paths.env_value("WIDGET") == "7"
    assert _iris_paths.env_value("QUOTED") == "a # b"       # '#' inside quotes preserved


def test_env_value_env_overrides_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    (tmp_path / ".env").write_text("FOO=from_dotenv\n")
    monkeypatch.setenv("FOO", "from_env")
    assert _iris_paths.env_value("FOO") == "from_env"


def test_env_value_default_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_ROOT", str(tmp_path))
    monkeypatch.delenv("NOPE", raising=False)
    assert _iris_paths.env_value("NOPE", "fallback") == "fallback"
