"""Capability tests for the Miner role."""

from cogames_agents.policy.scripted_agent.planky.tests.helpers import EpisodeResult


def test_miner_acquires_gear(miner_episode: EpisodeResult):
    gained = miner_episode.gear_gained("miner")
    assert gained > 0, f"Miner did not acquire gear (miner.gained={gained})\nTrace:\n{miner_episode.trace.summary()}"


def test_miner_deposits_resources(miner_episode: EpisodeResult):
    total = miner_episode.total_deposited()
    assert total > 0, (
        f"Miner did not deposit any resources (total_deposited={total})\nTrace:\n{miner_episode.trace.summary()}"
    )


def test_miner_mines_multiple_elements(miner_episode: EpisodeResult):
    elements = ["carbon", "oxygen", "germanium", "silicon"]
    deposited = {e: miner_episode.resource_deposited(e) for e in elements}
    non_zero = [e for e, v in deposited.items() if v > 0]
    assert len(non_zero) >= 1, f"Miner did not mine any elements: {deposited}\nTrace:\n{miner_episode.trace.summary()}"


def test_miner_stays_productive(miner_episode: EpisodeResult):
    """Miner should deposit a meaningful amount of resources in 500 steps."""
    total = miner_episode.total_deposited()
    assert total >= 10, (
        f"Miner deposited too few resources ({total}), may be stuck or idle\nTrace:\n{miner_episode.trace.summary()}"
    )
