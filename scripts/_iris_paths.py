"""Shared path resolution for iris scripts.

Iris is installed alongside a consuming project. Scripts must resolve
'repo root' to the *consumer's* directory, not to iris's own checkout.
This module centralises that logic so every script agrees.
"""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Resolve the consuming project's root.

    Order:
      1. $IRIS_ROOT  (explicit override — tests + embedded installs)
      2. current working directory (Claude Code's open project)
    """
    explicit = os.environ.get("IRIS_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path.cwd().resolve()


def handovers_dir() -> Path:
    return repo_root() / "handovers"


def state_dir() -> Path:
    return repo_root() / ".iris-state"


def plan_path() -> Path:
    rel = os.environ.get("PLAN_PATH", "docs/plan.md")
    p = Path(rel)
    return p if p.is_absolute() else repo_root() / p


def env_file() -> Path:
    return repo_root() / ".env"


# scripts/ itself is always iris's own scripts/ (where this helper lives).
SCRIPTS_DIR = Path(__file__).resolve().parent
