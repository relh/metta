"""Capability tests for the Scout role."""

from cogames_agents.policy.scripted_agent.planky.tests.helpers import EpisodeResult


def test_scout_acquires_gear(scout_episode: EpisodeResult):
    gained = scout_episode.gear_gained("scout")
    assert gained > 0, f"Scout did not acquire gear (scout.gained={gained})\nTrace:\n{scout_episode.trace.summary()}"


def test_scout_explores(scout_episode: EpisodeResult):
    """Scout should be actively exploring (Explore goal activated in trace)."""
    assert scout_episode.trace.had_goal("Explore"), (
        f"Scout never activated Explore goal\nTrace:\n{scout_episode.trace.summary()}"
    )
