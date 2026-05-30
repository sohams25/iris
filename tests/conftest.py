"""Shared pytest fixtures for iris tests."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def scripts_dir(repo_root) -> Path:
    return repo_root / "scripts"


@pytest.fixture
def hooks_dir(repo_root) -> Path:
    return repo_root / ".claude" / "hooks"
