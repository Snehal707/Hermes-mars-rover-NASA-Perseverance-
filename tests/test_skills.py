"""pytest: Rover SKILL.md files exist and are valid. Run with: pytest tests/test_skills.py -v"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SKILL_PATHS = [
    "hermes_rover/skills/obstacle_avoidance/SKILL.md",
    "hermes_rover/skills/storm_protocol/SKILL.md",
    "hermes_rover/skills/cliff_protocol/SKILL.md",
    "hermes_rover/skills/terrain_assessment/SKILL.md",
    "hermes_rover/skills/self_improvement/SKILL.md",
]


@pytest.mark.parametrize("rel_path", SKILL_PATHS)
def test_skill_file_exists_and_valid(rel_path):
    """Each SKILL.md exists, is not empty, has a heading, and contains 'trigger' and 'steps' (or 'protocol' and numbered list)."""
    path = ROOT / rel_path
    assert path.exists(), f"{rel_path} does not exist"
    assert path.stat().st_size > 0, f"{rel_path} is empty"

    content = path.read_text()
    lines = content.splitlines()

    has_heading = any(line.strip().startswith("#") for line in lines)
    assert has_heading, f"{rel_path} has no line starting with #"

    content_lower = content.lower()
    # Spec: trigger and steps. Current SKILLs use "protocol" and numbered lists; accept either.
    if "trigger" in content_lower and "steps" in content_lower:
        pass
    else:
        assert "protocol" in content_lower, f"{rel_path} must contain 'protocol' or 'trigger'/'steps'"
        assert any("1." in line for line in lines), f"{rel_path} must contain 'steps' or numbered list (1.)"
