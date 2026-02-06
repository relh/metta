"""Tests for Planky's role-switching behavior."""

from cogames_agents.policy.scripted_agent.planky.tests.helpers import run_planky_episode


def test_disable_role_switching_prevents_miner_to_aligner_conversion():
    collective_initial = {"carbon": 200, "oxygen": 200, "germanium": 200, "silicon": 200}

    enabled = run_planky_episode(
        policy_uri="metta://policy/planky?miner=8&aligner=0&trace=1&trace_level=2&trace_agent=0",
        steps=30,
        collective_initial=collective_initial,
    )
    assert any("miner→aligner" in line for line in enabled.trace.role_changes), (
        f"Expected miner→aligner conversion when role switching is enabled.\nTrace:\n{enabled.trace.summary()}"
    )

    disabled = run_planky_episode(
        policy_uri=(
            "metta://policy/planky?miner=8&aligner=0&disable_role_switching=1&trace=1&trace_level=2&trace_agent=0"
        ),
        steps=30,
        collective_initial=collective_initial,
    )
    assert not disabled.trace.role_changes, (
        f"Expected no role changes when disable_role_switching=1.\nTrace:\n{disabled.trace.summary()}"
    )
