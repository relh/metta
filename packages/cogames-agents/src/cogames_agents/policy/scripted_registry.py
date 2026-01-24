"""Registry of scripted policy URIs for teachers and scripted agent evaluation."""

from __future__ import annotations

SCRIPTED_AGENT_URIS: dict[str, str] = {
    "baseline": "metta://policy/baseline",
    "starter": "metta://policy/starter",
    "tiny_baseline": "metta://policy/tiny_baseline",
    "ladybug": "metta://policy/ladybug",
    "thinky": "metta://policy/thinky",
    "race_car": "metta://policy/race_car",
    "nim_ladybug": "metta://policy/nim_ladybug",
    "nim_random": "metta://policy/nim_random",
    "nim_cogsguard": "metta://policy/nim_cogsguard",
    "cogsguard": "metta://policy/cogsguard",
    "teacher": "metta://policy/teacher",
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
