from __future__ import annotations

import pytest
from cogames_agents.policy.scripted_registry import resolve_scripted_agent_uri


def test_resolve_scripted_agent_uri_known() -> None:
    assert resolve_scripted_agent_uri("baseline") == "metta://policy/baseline"
    assert resolve_scripted_agent_uri("thinky") == "metta://policy/thinky"
    assert resolve_scripted_agent_uri("miner") == "metta://policy/miner"


def test_resolve_scripted_agent_uri_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown scripted agent"):
        resolve_scripted_agent_uri("not-a-real-agent")
