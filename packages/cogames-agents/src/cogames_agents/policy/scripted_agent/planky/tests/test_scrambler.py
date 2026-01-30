"""Capability tests for the Scrambler role."""

import pytest

from cogames_agents.policy.scripted_agent.planky.tests.helpers import EpisodeResult


def test_scrambler_acquires_gear(scrambler_episode: EpisodeResult):
    gained = scrambler_episode.gear_gained("scrambler")
    assert gained > 0, (
        f"Scrambler did not acquire gear (scrambler.gained={gained})\nTrace:\n{scrambler_episode.trace.summary()}"
    )


def test_scrambler_acquires_hearts(scrambler_episode: EpisodeResult):
    hearts = scrambler_episode.hearts_gained()
    assert hearts > 0, (
        f"Scrambler did not acquire hearts (heart.gained={hearts})\nTrace:\n{scrambler_episode.trace.summary()}"
    )


@pytest.mark.xfail(reason="Scrambler cannot reach enemy junctions in 500 steps with limited economy")
def test_scrambler_scrambles_junctions(scrambler_episode: EpisodeResult):
    # Check for scrambled junctions in clips stats (enemy junctions neutralized)
    clips_aligned = int(scrambler_episode.clips_stats.get("junction.lost", 0))
    assert clips_aligned > 0, (
        f"Scrambler did not scramble any enemy junctions (clips junction.lost={clips_aligned})\n"
        f"Trace:\n{scrambler_episode.trace.summary()}"
    )
