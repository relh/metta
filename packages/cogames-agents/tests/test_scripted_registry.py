from __future__ import annotations

import pytest
from cogames_agents.policy.scripted_registry import resolve_scripted_agent_uri


def test_resolve_scripted_agent_uri_known() -> None:
    assert resolve_scripted_agent_uri("baseline") == "metta://policy/baseline"
    assert resolve_scripted_agent_uri("thinky") == "metta://policy/thinky"
    assert resolve_scripted_agent_uri("thinky_nim") == "metta://policy/thinky_nim"
    assert resolve_scripted_agent_uri("ladybug") == "metta://policy/ladybug"
    assert resolve_scripted_agent_uri("ladybug_py") == "metta://policy/ladybug_py"
    assert resolve_scripted_agent_uri("ladybug_nim") == "metta://policy/ladybug_nim"
    assert resolve_scripted_agent_uri("race_car") == "metta://policy/race_car"
    assert resolve_scripted_agent_uri("race_car_nim") == "metta://policy/race_car_nim"
    assert resolve_scripted_agent_uri("nim_random") == "metta://policy/nim_random"
    assert resolve_scripted_agent_uri("random_nim") == "metta://policy/random_nim"
    assert resolve_scripted_agent_uri("role") == "metta://policy/role"
    assert resolve_scripted_agent_uri("role_nim") == "metta://policy/role_nim"
    assert resolve_scripted_agent_uri("role_py") == "metta://policy/role_py"
    assert resolve_scripted_agent_uri("wombo") == "metta://policy/wombo"
    assert resolve_scripted_agent_uri("alignall") == "metta://policy/alignall"
    assert resolve_scripted_agent_uri("teacher") == "metta://policy/teacher"
    assert resolve_scripted_agent_uri("teacher_nim") == "metta://policy/teacher_nim"
    assert resolve_scripted_agent_uri("miner") == "metta://policy/miner"


def test_resolve_scripted_agent_uri_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown scripted agent"):
        resolve_scripted_agent_uri("not-a-real-agent")
