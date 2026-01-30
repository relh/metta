"""Capability tests for the Aligner role."""

from cogames_agents.policy.scripted_agent.planky.tests.helpers import EpisodeResult


def test_aligner_acquires_gear(aligner_episode: EpisodeResult):
    gained = aligner_episode.gear_gained("aligner")
    assert gained > 0, (
        f"Aligner did not acquire gear (aligner.gained={gained})\nTrace:\n{aligner_episode.trace.summary()}"
    )


def test_aligner_acquires_hearts(aligner_episode: EpisodeResult):
    hearts = aligner_episode.hearts_gained()
    assert hearts > 0, (
        f"Aligner did not acquire hearts (heart.gained={hearts})\nTrace:\n{aligner_episode.trace.summary()}"
    )


def test_aligner_aligns_junctions(aligner_episode: EpisodeResult):
    aligned = aligner_episode.junctions_aligned()
    assert aligned > 0, (
        f"Aligner did not align any junctions (junction.gained={aligned})\nTrace:\n{aligner_episode.trace.summary()}"
    )
