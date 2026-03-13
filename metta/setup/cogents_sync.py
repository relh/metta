from __future__ import annotations

import re
from pathlib import Path

_SHARED_SKILLS_HEADER = "## Shared Skill List"
_SKILL_BULLET_PATTERN = re.compile(r"- (.+)$")
_SKILL_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


def parse_shared_skill_names(rules_text: str) -> list[str]:
    in_shared_skills = False
    skill_names: list[str] = []

    for raw_line in rules_text.splitlines():
        line = raw_line.strip()

        if line == _SHARED_SKILLS_HEADER:
            in_shared_skills = True
            continue

        if not in_shared_skills:
            continue

        if line.startswith("## "):
            break

        match = _SKILL_BULLET_PATTERN.fullmatch(line)
        if not match:
            continue

        skill_name = match.group(1).strip()
        if skill_name.startswith("`") and skill_name.endswith("`"):
            skill_name = skill_name[1:-1].strip()

        if _SKILL_NAME_PATTERN.fullmatch(skill_name):
            skill_names.append(skill_name)

    return skill_names


def load_shared_skill_names(repo_root: Path) -> list[str]:
    rules_path = repo_root / ".cursor" / "rules" / "skills.mdc"
    return parse_shared_skill_names(rules_path.read_text())


def missing_shared_skills(repo_root: Path, skills_dir: Path) -> list[str]:
    return [
        skill_name
        for skill_name in load_shared_skill_names(repo_root)
        if not (skills_dir / skill_name / "SKILL.md").is_file()
    ]
