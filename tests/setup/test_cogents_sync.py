from pathlib import Path

import pytest

from metta.setup.cogents_sync import missing_shared_skills, parse_shared_skill_names

pytestmark = pytest.mark.setup


def test_parse_shared_skill_names_stops_at_next_section() -> None:
    rules_text = """
## Shared Skill List

- rl.research.begin
- `rl.research.begin`
- `rl.research.task-characterize`
- rl.analyze.begin

## How to Use

- `should.not.parse`
"""

    assert parse_shared_skill_names(rules_text) == [
        "rl.research.begin",
        "rl.research.begin",
        "rl.research.task-characterize",
        "rl.analyze.begin",
    ]


def test_missing_shared_skills_reports_missing_entries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_dir = repo_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "skills.mdc").write_text(
        """
## Shared Skill List

- `rl.research.begin`
- `rl.research.task-characterize`

## How to Use
"""
    )

    skills_dir = tmp_path / "skills"
    present_skill_dir = skills_dir / "rl.research.begin"
    present_skill_dir.mkdir(parents=True)
    (present_skill_dir / "SKILL.md").write_text("---\nname: rl.research.begin\n---\n")

    assert missing_shared_skills(repo_root, skills_dir) == ["rl.research.task-characterize"]
