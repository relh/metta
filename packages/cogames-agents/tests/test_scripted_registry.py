from __future__ import annotations

import pytest
from cogames_agents.policy.scripted_registry import resolve_scripted_agent_uri


def test_resolve_scripted_agent_uri_known() -> None:
    assert resolve_scripted_agent_uri("baseline") == "metta://policy/baseline"
    assert resolve_scripted_agent_uri("thinky") == "metta://policy/thinky"
    assert resolve_scripted_agent_uri("ladybug") == "metta://policy/ladybug"
    assert resolve_scripted_agent_uri("ladybug_py") == "metta://policy/ladybug_py"
    assert resolve_scripted_agent_uri("cogsguard") == "metta://policy/cogsguard"
    assert resolve_scripted_agent_uri("cogsguard_py") == "metta://policy/cogsguard_py"
    assert resolve_scripted_agent_uri("miner") == "metta://policy/miner"


def test_resolve_scripted_agent_uri_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown scripted agent"):
        resolve_scripted_agent_uri("not-a-real-agent")
