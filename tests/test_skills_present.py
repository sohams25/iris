"""Every owned skill ships a SKILL.md with valid frontmatter.

`setup.sh` symlinks these four into each consumer's `.claude/skills/`, so a
missing or malformed SKILL.md silently breaks skill loading downstream.
"""
from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a declared dependency
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
OWNED = ["handovers", "swarm", "commit-style", "karpathy-guidelines"]


def _frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


@pytest.mark.skipif(yaml is None, reason="PyYAML not installed")
@pytest.mark.parametrize("skill", OWNED)
def test_owned_skill_has_valid_frontmatter(skill):
    skill_md = SKILLS_DIR / skill / "SKILL.md"
    assert skill_md.exists(), f"{skill}/SKILL.md missing"
    fm = _frontmatter(skill_md.read_text(encoding="utf-8"))
    assert fm.get("name"), f"{skill}: missing 'name' in frontmatter"
    assert fm.get("description"), f"{skill}: missing 'description' in frontmatter"


def test_karpathy_skill_vendored_with_attribution():
    d = SKILLS_DIR / "karpathy-guidelines"
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "license: MIT" in skill
    assert "andrej-karpathy-skills" in skill  # provenance preserved
    assert (d / "EXAMPLES.md").exists()
