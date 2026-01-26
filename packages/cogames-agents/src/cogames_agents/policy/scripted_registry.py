"""Registry of scripted policy URIs for teachers and scripted agent evaluation."""

from __future__ import annotations

SCRIPTED_AGENT_URIS: dict[str, str] = {
    "baseline": "metta://policy/baseline",
    "starter": "metta://policy/starter",
    "tiny_baseline": "metta://policy/tiny_baseline",
    "ladybug": "metta://policy/ladybug",
    "ladybug_nim": "metta://policy/ladybug_nim",
    "ladybug_py": "metta://policy/ladybug_py",
    "thinky": "metta://policy/thinky",
    "thinky_nim": "metta://policy/thinky_nim",
    "race_car": "metta://policy/race_car",
    "race_car_nim": "metta://policy/race_car_nim",
    "nim_random": "metta://policy/nim_random",
    "random_nim": "metta://policy/random_nim",
    "cogsguard": "metta://policy/cogsguard",
    "cogsguard_nim": "metta://policy/cogsguard_nim",
    "cogsguard_py": "metta://policy/cogsguard_py",
    "cogsguard_align_all": "metta://policy/cogsguard_align_all",
    "teacher": "metta://policy/teacher",
    "teacher_nim": "metta://policy/teacher_nim",
    "miner": "metta://policy/miner",
    "scout": "metta://policy/scout",
    "aligner": "metta://policy/aligner",
    "scrambler": "metta://policy/scrambler",
}


def resolve_scripted_agent_uri(name: str) -> str:
    if name in SCRIPTED_AGENT_URIS:
        return SCRIPTED_AGENT_URIS[name]
    available = ", ".join(sorted(SCRIPTED_AGENT_URIS))
    raise ValueError(f"Unknown scripted agent '{name}'. Available: {available}")
