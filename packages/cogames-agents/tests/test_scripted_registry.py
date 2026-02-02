from __future__ import annotations

import pytest
from cogames_agents.policy.scripted_registry import list_scripted_agent_names, resolve_scripted_agent_uri


def test_resolve_scripted_agent_uri_known() -> None:
    names = set(list_scripted_agent_names())
    expected = {
        "alignall",
        "aligner",
        "baseline",
        "cogsguard_control",
        "cogsguard_targeted",
        "cogsguard_v2",
        "miner",
        "nim_random",
        "race_car",
        "role",
        "role_py",
        "scout",
        "scrambler",
        "teacher",
        "thinky",
        "tiny_baseline",
        "wombo",
    }
    assert expected.issubset(names)
    for name in expected:
        assert resolve_scripted_agent_uri(name) == f"metta://policy/{name}"


def test_resolve_scripted_agent_uri_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown scripted agent"):
        resolve_scripted_agent_uri("not-a-real-agent")
