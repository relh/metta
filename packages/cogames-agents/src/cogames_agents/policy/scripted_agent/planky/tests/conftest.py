"""Shared fixtures for Planky capability tests."""

import pytest

from cogames_agents.policy.scripted_agent.planky.tests.helpers import (
    EpisodeResult,
    run_planky_episode,
)

MISSION = "cogsguard_machina_1.basic"
DEFAULT_STEPS = 500
DEFAULT_SEED = 42


@pytest.fixture(scope="module")
def miner_episode() -> EpisodeResult:
    return run_planky_episode(
        policy_uri="metta://policy/planky?miner=1&aligner=0&trace=1&trace_level=2&trace_agent=0",
        mission=MISSION,
        steps=DEFAULT_STEPS,
        seed=DEFAULT_SEED,
    )


@pytest.fixture(scope="module")
def aligner_episode() -> EpisodeResult:
    """Aligner needs miners to fund gear + hearts."""
    return run_planky_episode(
        policy_uri="metta://policy/planky?miner=4&aligner=1&scrambler=0&trace=1&trace_level=2&trace_agent=4",
        mission=MISSION,
        steps=DEFAULT_STEPS,
        seed=DEFAULT_SEED,
    )


@pytest.fixture(scope="module")
def scrambler_episode() -> EpisodeResult:
    """Scrambler needs miners to fund gear + hearts."""
    return run_planky_episode(
        policy_uri="metta://policy/planky?miner=4&aligner=0&scrambler=1&trace=1&trace_level=2&trace_agent=4",
        mission=MISSION,
        steps=DEFAULT_STEPS,
        seed=DEFAULT_SEED,
    )


@pytest.fixture(scope="module")
def scout_episode() -> EpisodeResult:
    """Scout needs miners to fund gear."""
    return run_planky_episode(
        policy_uri="metta://policy/planky?miner=4&aligner=0&scout=1&trace=1&trace_level=2&trace_agent=4",
        mission=MISSION,
        steps=DEFAULT_STEPS,
        seed=DEFAULT_SEED,
    )


@pytest.fixture(scope="module")
def stem_episode() -> EpisodeResult:
    """Full stem=5 run — tests dynamic role selection + pipeline."""
    return run_planky_episode(
        policy_uri="metta://policy/planky?stem=5&trace=1&trace_level=2",
        mission=MISSION,
        steps=DEFAULT_STEPS,
        seed=DEFAULT_SEED,
    )
