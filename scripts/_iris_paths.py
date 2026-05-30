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


def env_value(key: str, default: str = "") -> str:
    """Resolve a config value: $KEY in the environment, else `KEY=` in .env,
    else the default. Tolerates an `export ` prefix, surrounding quotes, and a
    trailing ` # comment` (comments inside quotes are preserved)."""
    v = os.environ.get(key, "").strip()
    if v:
        return v
    ef = env_file()
    if ef.exists():
        for line in ef.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("export "):
                s = s[len("export "):].lstrip()
            if s.startswith("#") or not s.startswith(f"{key}="):
                continue
            val = s.partition("=")[2].strip()
            if val[:1] in ("'", '"'):
                quote = val[0]
                val = val[1:]
                return val[: val.index(quote)] if quote in val else val
            return val.split(" #", 1)[0].rstrip()
    return default


def next_path() -> Path:
    """The plan-ahead queue file ($NEXT_PATH, default docs/next.md)."""
    rel = env_value("NEXT_PATH", "docs/next.md")
    p = Path(rel)
    return p if p.is_absolute() else repo_root() / p


# scripts/ itself is always iris's own scripts/ (where this helper lives).
SCRIPTS_DIR = Path(__file__).resolve().parent
