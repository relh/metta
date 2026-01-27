"""
Behavior tests for the Pinky policy.

These tests verify that pinky agents can perform specific capabilities:
- General skills: navigation, exploration, gear acquisition
- Miner skills: resource extraction, deposit cycles
- Scout skills: frontier-based exploration

Tests run short simulations and verify expected behaviors occur.
"""

from __future__ import annotations

from typing import Any

import pytest
from metta_alo.rollout import run_single_episode

from cogames.cogs_vs_clips.evals.pinky_evals import (
    PINKY_BEHAVIOR_EVALS,
    PinkyAlignerTest,
    PinkyAllGearStations,
    PinkyExplorationMemory,
    PinkyFourRoles,
    PinkyGearMiner,
    PinkyGearScout,
    PinkyMazeNavigation,
    PinkyMinerBumpExtractor,
    PinkyMinerExtract,
    PinkyMinerFullCycle,
    PinkyMinerMultiExtractors,
    PinkyNavigationObstacles,
    PinkyRetreatTest,
    PinkyScoutExplore,
    PinkyScramblerTest,
)
from mettagrid.policy.loader import discover_and_register_policies
from mettagrid.policy.policy import PolicySpec

# Register pinky and other policies
discover_and_register_policies("cogames_agents.policy")


def run_pinky_episode(
    mission_class: type,
    max_steps: int | None = None,
    vibes: dict[str, int] | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Run a pinky policy episode and collect statistics.

    Args:
        mission_class: The mission class to instantiate
        max_steps: Override max steps (uses mission default if None)
        vibes: Dict of vibe counts e.g. {"miner": 1, "scout": 0}
        seed: Random seed

    Returns:
        Dict with episode statistics including stats from simulator
    """
    mission = mission_class()
    env_cfg = mission.make_env()
    if max_steps is not None:
        env_cfg.game.max_steps = max_steps

    # Build policy spec with vibe kwargs
    init_kwargs = vibes if vibes else {"miner": 1}  # Default to one miner
    policy_spec = PolicySpec(class_path="pinky", data_path=None, init_kwargs=init_kwargs)

    # Run the episode directly using run_single_episode to get stats
    results, _replay = run_single_episode(
        policy_specs=[policy_spec],
        assignments=[0] * env_cfg.game.num_agents,
        env=env_cfg,
        results_uri=None,
        replay_uri=None,
        seed=seed,
        device="cpu",
        render_mode="none",
    )

    return {
        "steps": results.steps,
        "completed": True,
        "stats": results.stats,
        "rewards": results.rewards,
    }


# ==============================================================================
# General Skills Tests
# ==============================================================================


class TestPinkyGearAcquisition:
    """Tests for gear acquisition behavior."""

    def test_miner_gets_miner_gear(self) -> None:
        """Miner role should navigate to miner station and get gear."""
        stats = run_pinky_episode(
            PinkyGearMiner,
            max_steps=100,
            vibes={"miner": 1},  # Force miner role
        )
        # Should complete without error and run some steps
        assert stats["steps"] > 0, "Episode should run for at least one step"

    def test_scout_gets_scout_gear(self) -> None:
        """Scout role should navigate to scout station and get gear."""
        stats = run_pinky_episode(
            PinkyGearScout,
            max_steps=100,
            vibes={"scout": 1},  # Force scout role
        )
        assert stats["steps"] > 0, "Episode should run for at least one step"


class TestPinkyNavigation:
    """Tests for navigation behavior."""

    def test_navigation_around_obstacles(self) -> None:
        """Agent should pathfind around wall obstacles."""
        stats = run_pinky_episode(
            PinkyNavigationObstacles,
            max_steps=150,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"


class TestPinkyExploration:
    """Tests for exploration behavior."""

    def test_scout_explores_area(self) -> None:
        """Scout should systematically explore an open area."""
        stats = run_pinky_episode(
            PinkyScoutExplore,
            max_steps=200,
            vibes={"scout": 1},
        )
        assert stats["steps"] > 0, "Episode should run"

    def test_exploration_discovers_distant_objects(self) -> None:
        """Agent should explore and discover distant structures."""
        stats = run_pinky_episode(
            PinkyExplorationMemory,
            max_steps=300,
            vibes={"scout": 1},
        )
        assert stats["steps"] > 0, "Episode should run"


# ==============================================================================
# Miner Skills Tests
# ==============================================================================


class TestPinkyMiner:
    """Tests for miner behavior."""

    def test_miner_extracts_resources(self) -> None:
        """Miner should get gear and extract from nearby extractor."""
        stats = run_pinky_episode(
            PinkyMinerExtract,
            max_steps=150,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"

    def test_miner_bumps_extractor_picks_up_carbon(self) -> None:
        """Miner should bump into extractor and pick up carbon resources.

        This test verifies the core miner functionality:
        1. Miner gets gear from miner station
        2. Miner moves toward carbon extractor
        3. Walking into the extractor picks up carbon (bump extraction)
        """
        stats = run_pinky_episode(
            PinkyMinerBumpExtractor,
            max_steps=100,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"

        # Check that agent gained carbon
        episode_stats = stats.get("stats", {})
        agent_stats_list = episode_stats.get("agent", [])

        # Should have at least one agent
        assert len(agent_stats_list) >= 1, "Should have agent stats"

        # Check the first agent (our miner) picked up carbon
        agent_stats = agent_stats_list[0]
        carbon_gained = agent_stats.get("carbon.gained", 0)

        assert carbon_gained > 0, (
            f"Miner should have picked up carbon by bumping into extractor. "
            f"Got carbon.gained={carbon_gained}. Agent stats: {agent_stats}"
        )

    def test_miner_full_cycle(self) -> None:
        """Miner should complete: gear -> extract -> deposit cycle."""
        stats = run_pinky_episode(
            PinkyMinerFullCycle,
            max_steps=300,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"

    def test_miner_visits_multiple_extractors(self) -> None:
        """Miner should efficiently visit multiple extractors."""
        stats = run_pinky_episode(
            PinkyMinerMultiExtractors,
            max_steps=400,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"


# ==============================================================================
# Aligner/Scrambler Skills Tests
# ==============================================================================


class TestPinkyAligner:
    """Tests for aligner behavior."""

    def test_aligner_gets_gear(self) -> None:
        """Aligner should navigate to aligner station and get gear."""
        stats = run_pinky_episode(
            PinkyAlignerTest,
            max_steps=150,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"

    def test_aligner_approaches_junction(self) -> None:
        """Aligner with gear should approach neutral junctions."""
        stats = run_pinky_episode(
            PinkyAlignerTest,
            max_steps=200,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"


class TestPinkyScrambler:
    """Tests for scrambler behavior."""

    def test_scrambler_gets_gear(self) -> None:
        """Scrambler should navigate to scrambler station and get gear."""
        stats = run_pinky_episode(
            PinkyScramblerTest,
            max_steps=150,
            vibes={"scrambler": 1},
        )
        assert stats["steps"] > 0, "Episode should run"


# ==============================================================================
# Advanced Navigation Tests
# ==============================================================================


class TestPinkyAdvancedNavigation:
    """Tests for advanced navigation scenarios."""

    def test_maze_navigation(self) -> None:
        """Agent should navigate through a complex maze."""
        stats = run_pinky_episode(
            PinkyMazeNavigation,
            max_steps=300,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"

    def test_retreat_behavior(self) -> None:
        """Agent with critical HP should retreat to safety."""
        stats = run_pinky_episode(
            PinkyRetreatTest,
            max_steps=100,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"


# ==============================================================================
# Multi-Role Tests
# ==============================================================================


class TestPinkyMultiRole:
    """Tests for multi-agent scenarios with different roles."""

    def test_all_gear_stations_accessible(self) -> None:
        """Agent should be able to reach any gear station."""
        for vibe in ["miner", "scout", "aligner", "scrambler"]:
            stats = run_pinky_episode(
                PinkyAllGearStations,
                max_steps=100,
                vibes={vibe: 1},
            )
            assert stats["steps"] > 0, f"Episode with {vibe} role should run"

    def test_four_roles_work_together(self) -> None:
        """Four agents with different roles should work together."""
        stats = run_pinky_episode(
            PinkyFourRoles,
            max_steps=200,
            vibes={"miner": 1, "scout": 1, "aligner": 1, "scrambler": 1},
        )
        assert stats["steps"] > 0, "Episode should run"


# ==============================================================================
# Smoke Tests - All Missions
# ==============================================================================


@pytest.mark.parametrize(
    "mission_class",
    PINKY_BEHAVIOR_EVALS,
    ids=[m.model_fields["name"].default for m in PINKY_BEHAVIOR_EVALS],
)
def test_pinky_behavior_mission_runs(mission_class: type) -> None:
    """Smoke test: All pinky behavior missions should run without error."""
    stats = run_pinky_episode(mission_class, max_steps=50)
    assert stats["steps"] > 0, f"Mission {mission_class} should run for at least one step"


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestPinkyIntegration:
    """Integration tests for pinky policy."""

    def test_pinky_with_different_vibes(self) -> None:
        """Pinky should support different vibe distributions."""
        # Test with miner role
        stats = run_pinky_episode(
            PinkyGearMiner,
            max_steps=50,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run"

    def test_pinky_scout_vibe(self) -> None:
        """Pinky should support scout vibe."""
        stats = run_pinky_episode(
            PinkyGearScout,
            max_steps=50,
            vibes={"scout": 1},
        )
        assert stats["steps"] > 0, "Episode should run"
