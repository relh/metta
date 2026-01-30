"""Capability tests for the Stem (dynamic role selection) system."""

from cogames_agents.policy.scripted_agent.planky.tests.helpers import EpisodeResult


def test_stem_agents_select_roles(stem_episode: EpisodeResult):
    changes = stem_episode.trace.role_changes
    assert len(changes) > 0, f"No role changes detected in trace\nTrace:\n{stem_episode.trace.summary()}"


def test_stem_multiple_roles_represented(stem_episode: EpisodeResult):
    roles_seen = set()
    for line in stem_episode.trace.role_changes:
        # Format: "[planky][t=5 a=1] role: stem→miner"
        if "→" in line:
            role = line.split("→")[-1].strip()
            roles_seen.add(role)
    assert len(roles_seen) >= 2, (
        f"Only {len(roles_seen)} role(s) selected: {roles_seen}. "
        f"Expected at least 2 distinct roles.\n"
        f"Trace:\n{stem_episode.trace.summary()}"
    )


def test_stem_economy_produces_resources(stem_episode: EpisodeResult):
    total = stem_episode.total_deposited()
    assert total > 0, (
        f"Stem team did not deposit any resources (total_deposited={total})\nTrace:\n{stem_episode.trace.summary()}"
    )


def test_stem_pipeline_aligns_junctions(stem_episode: EpisodeResult):
    aligned = stem_episode.junctions_aligned()
    assert aligned > 0, (
        f"Stem team did not align any junctions (junction.gained={aligned})\nTrace:\n{stem_episode.trace.summary()}"
    )
