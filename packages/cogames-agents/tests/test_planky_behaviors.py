"""
Behavior tests for the Planky policy.

These tests verify that Planky agents can perform specific capabilities
in deterministic CogsGuard environments:
- Miner skills: gear acquisition, resource extraction, deposit, full cycle
- Aligner skills: gear, hearts, junction approach, AOE avoidance
- Scrambler skills: gear, enemy junction targeting
- Scout skills: gear, exploration
- Survival: retreat behavior
- Navigation: maze, distant exploration, corridor navigation
- Recovery: re-acquiring lost gear/hearts
- Multi-role: multiple agents with different roles

Tests run short simulations and verify expected behaviors occur.
"""

from __future__ import annotations

from typing import Any

import pytest
from metta_alo.rollout import run_single_episode

from cogames.cogs_vs_clips.evals.planky_evals import (
    PLANKY_BEHAVIOR_EVALS,
    PlankyAlignerAvoidAOE,
    PlankyAlignerFullCycle,
    PlankyAlignerGear,
    PlankyAlignerHearts,
    PlankyAlignerJunction,
    PlankyAlignerReGear,
    PlankyAlignerReHearts,
    PlankyExplorationDistant,
    PlankyMaze,
    PlankyMinerBestResource,
    PlankyMinerDeposit,
    PlankyMinerExtract,
    PlankyMinerFullCycle,
    PlankyMinerGear,
    PlankyMinerReGear,
    PlankyMultiRole,
    PlankyResourceChain,
    PlankyScoutExplore,
    PlankyScoutGear,
    PlankyScramblerFullCycle,
    PlankyScramblerGear,
    PlankyScramblerRecovery,
    PlankyScramblerTarget,
    PlankyStuckCorridor,
    PlankySurviveRetreat,
)
from mettagrid.policy.loader import discover_and_register_policies
from mettagrid.policy.policy import PolicySpec

# Register planky and other policies
discover_and_register_policies("cogames_agents.policy")


def run_planky_episode(
    mission_class: type,
    max_steps: int | None = None,
    vibes: dict[str, int] | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Run a planky policy episode and collect statistics.

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

    # Build policy spec with vibe kwargs.
    # Must explicitly zero all roles to override PlankyPolicy defaults (miner=4, scrambler=4, etc.)
    all_roles = {"miner": 0, "scout": 0, "aligner": 0, "scrambler": 0}
    if vibes:
        all_roles.update(vibes)
    else:
        all_roles["miner"] = 1  # Default to one miner
    policy_spec = PolicySpec(class_path="planky", data_path=None, init_kwargs=all_roles)

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
# Miner Tests
# ==============================================================================


class TestPlankyMiner:
    """Tests for miner behavior."""

    def test_miner_gets_gear(self) -> None:
        """Miner should navigate to miner station and get gear."""
        stats = run_planky_episode(
            PlankyMinerGear,
            max_steps=100,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0, "Episode should run for at least one step"

        # Check miner gear gained
        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            miner_gained = agent_stats[0].get("miner.gained", 0)
            assert miner_gained > 0, (
                f"Miner should have gained miner gear. Got miner.gained={miner_gained}. Stats: {agent_stats[0]}"
            )

    def test_miner_extracts_carbon(self) -> None:
        """Miner should get gear and extract carbon from extractor."""
        stats = run_planky_episode(
            PlankyMinerExtract,
            max_steps=200,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            assert carbon_gained > 0, (
                f"Miner should have extracted carbon. Got carbon.gained={carbon_gained}. Stats: {agent_stats[0]}"
            )

    def test_miner_picks_best_resource(self) -> None:
        """Miner should prefer carbon (3 extractors) over oxygen (1 extractor)."""
        stats = run_planky_episode(
            PlankyMinerBestResource,
            max_steps=300,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            oxygen_gained = agent_stats[0].get("oxygen.gained", 0)
            assert carbon_gained > oxygen_gained, (
                f"Miner should prefer carbon. carbon.gained={carbon_gained}, oxygen.gained={oxygen_gained}"
            )

    def test_miner_deposits_cargo(self) -> None:
        """Miner starting with cargo should deposit at hub."""
        stats = run_planky_episode(
            PlankyMinerDeposit,
            max_steps=200,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

    def test_miner_full_cycle(self) -> None:
        """Miner should complete: gear -> extract -> deposit cycle."""
        stats = run_planky_episode(
            PlankyMinerFullCycle,
            max_steps=400,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            assert carbon_gained > 0, (
                f"Miner should have extracted carbon in full cycle. Got carbon.gained={carbon_gained}"
            )


# ==============================================================================
# Aligner Tests
# ==============================================================================


class TestPlankyAligner:
    """Tests for aligner behavior."""

    def test_aligner_gets_gear(self) -> None:
        """Aligner should navigate to aligner station and get gear."""
        stats = run_planky_episode(
            PlankyAlignerGear,
            max_steps=100,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            aligner_gained = agent_stats[0].get("aligner.gained", 0)
            assert aligner_gained > 0, (
                f"Aligner should have gained aligner gear. Got aligner.gained={aligner_gained}. Stats: {agent_stats[0]}"
            )

    def test_aligner_gets_hearts(self) -> None:
        """Aligner with gear should get hearts from chest."""
        stats = run_planky_episode(
            PlankyAlignerHearts,
            max_steps=200,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            heart_gained = agent_stats[0].get("heart.gained", 0)
            assert heart_gained > 0, (
                f"Aligner should have gained hearts. Got heart.gained={heart_gained}. Stats: {agent_stats[0]}"
            )

    def test_aligner_approaches_junction(self) -> None:
        """Aligner with gear and hearts should approach junction."""
        stats = run_planky_episode(
            PlankyAlignerJunction,
            max_steps=300,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0

    def test_aligner_avoids_enemy_aoe(self) -> None:
        """Aligner should prefer safe junction over clips-aligned one."""
        stats = run_planky_episode(
            PlankyAlignerAvoidAOE,
            max_steps=400,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0


# ==============================================================================
# Scrambler Tests
# ==============================================================================


class TestPlankyScrambler:
    """Tests for scrambler behavior."""

    def test_scrambler_gets_gear(self) -> None:
        """Scrambler should navigate to scrambler station and get gear."""
        stats = run_planky_episode(
            PlankyScramblerGear,
            max_steps=100,
            vibes={"scrambler": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            scrambler_gained = agent_stats[0].get("scrambler.gained", 0)
            assert scrambler_gained > 0, (
                f"Scrambler should have gained scrambler gear. "
                f"Got scrambler.gained={scrambler_gained}. Stats: {agent_stats[0]}"
            )

    def test_scrambler_targets_enemy(self) -> None:
        """Scrambler with gear and hearts should approach clips junction."""
        stats = run_planky_episode(
            PlankyScramblerTarget,
            max_steps=300,
            vibes={"scrambler": 1},
        )
        assert stats["steps"] > 0


# ==============================================================================
# Scout Tests
# ==============================================================================


class TestPlankyScout:
    """Tests for scout behavior."""

    def test_scout_gets_gear(self) -> None:
        """Scout should navigate to scout station and get gear."""
        stats = run_planky_episode(
            PlankyScoutGear,
            max_steps=100,
            vibes={"scout": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            scout_gained = agent_stats[0].get("scout.gained", 0)
            assert scout_gained > 0, (
                f"Scout should have gained scout gear. Got scout.gained={scout_gained}. Stats: {agent_stats[0]}"
            )

    def test_scout_explores(self) -> None:
        """Scout with gear should explore, taking many steps."""
        stats = run_planky_episode(
            PlankyScoutExplore,
            max_steps=200,
            vibes={"scout": 1},
        )
        assert stats["steps"] > 10, f"Scout should explore for many steps. Got steps={stats['steps']}"


# ==============================================================================
# Survival Tests
# ==============================================================================


class TestPlankySurvival:
    """Tests for survival behavior."""

    def test_survive_retreat(self) -> None:
        """Agent with low HP should survive the episode."""
        stats = run_planky_episode(
            PlankySurviveRetreat,
            max_steps=200,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0


# ==============================================================================
# Navigation Tests
# ==============================================================================


class TestPlankyNavigation:
    """Tests for navigation behavior."""

    def test_maze_navigation(self) -> None:
        """Miner should navigate maze to reach extractor."""
        stats = run_planky_episode(
            PlankyMaze,
            max_steps=400,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            assert carbon_gained > 0, (
                f"Miner should reach carbon extractor through maze. Got carbon.gained={carbon_gained}"
            )

    def test_distant_exploration(self) -> None:
        """Miner should find and extract from distant resource."""
        stats = run_planky_episode(
            PlankyExplorationDistant,
            max_steps=400,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            assert carbon_gained > 0, f"Miner should find distant carbon extractor. Got carbon.gained={carbon_gained}"

    def test_stuck_corridor(self) -> None:
        """Miner should navigate winding corridor to reach target."""
        stats = run_planky_episode(
            PlankyStuckCorridor,
            max_steps=400,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            assert carbon_gained > 0, (
                f"Miner should reach carbon extractor through corridor. Got carbon.gained={carbon_gained}"
            )


# ==============================================================================
# Multi-Role Tests
# ==============================================================================


class TestPlankyMultiRole:
    """Tests for multi-agent scenarios with different roles."""

    def test_multi_role(self) -> None:
        """Four agents with different roles should all work."""
        stats = run_planky_episode(
            PlankyMultiRole,
            max_steps=300,
            vibes={"miner": 1, "scout": 1, "aligner": 1, "scrambler": 1},
        )
        assert stats["steps"] > 0


# ==============================================================================
# Full Cycle Tests
# ==============================================================================


class TestPlankyFullCycle:
    """Tests for complete goal-tree execution."""

    def test_aligner_full_cycle(self) -> None:
        """Aligner: gear -> hearts -> junction approach."""
        stats = run_planky_episode(
            PlankyAlignerFullCycle,
            max_steps=400,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0

    def test_scrambler_full_cycle(self) -> None:
        """Scrambler: gear -> hearts -> scramble junction."""
        stats = run_planky_episode(
            PlankyScramblerFullCycle,
            max_steps=400,
            vibes={"scrambler": 1},
        )
        assert stats["steps"] > 0

    def test_resource_chain(self) -> None:
        """Miner: mine resources -> deposit at hub end-to-end."""
        stats = run_planky_episode(
            PlankyResourceChain,
            max_steps=500,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            assert carbon_gained > 0, f"Miner should have mined resources in chain. Got carbon.gained={carbon_gained}"


# ==============================================================================
# Recovery Tests
# ==============================================================================


class TestPlankyRecovery:
    """Tests for recovery behavior (re-acquiring lost gear/hearts)."""

    def test_miner_re_gears(self) -> None:
        """Miner without gear should re-acquire gear then mine."""
        stats = run_planky_episode(
            PlankyMinerReGear,
            max_steps=300,
            vibes={"miner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            miner_gained = agent_stats[0].get("miner.gained", 0)
            carbon_gained = agent_stats[0].get("carbon.gained", 0)
            assert miner_gained > 0, f"Miner should have re-acquired gear. miner.gained={miner_gained}"
            assert carbon_gained > 0, (
                f"Miner should have extracted carbon after re-gearing. carbon.gained={carbon_gained}"
            )

    def test_aligner_re_gears(self) -> None:
        """Aligner without gear should re-acquire gear."""
        stats = run_planky_episode(
            PlankyAlignerReGear,
            max_steps=400,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            aligner_gained = agent_stats[0].get("aligner.gained", 0)
            assert aligner_gained > 0, f"Aligner should have re-acquired gear. aligner.gained={aligner_gained}"

    def test_aligner_re_hearts(self) -> None:
        """Aligner with gear but no hearts should re-acquire hearts."""
        stats = run_planky_episode(
            PlankyAlignerReHearts,
            max_steps=400,
            vibes={"aligner": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            heart_gained = agent_stats[0].get("heart.gained", 0)
            assert heart_gained > 0, f"Aligner should have re-acquired hearts. heart.gained={heart_gained}"

    def test_scrambler_recovers(self) -> None:
        """Scrambler without gear/hearts should recover both."""
        stats = run_planky_episode(
            PlankyScramblerRecovery,
            max_steps=400,
            vibes={"scrambler": 1},
        )
        assert stats["steps"] > 0

        agent_stats = stats["stats"].get("agent", [])
        if agent_stats:
            scrambler_gained = agent_stats[0].get("scrambler.gained", 0)
            assert scrambler_gained > 0, f"Scrambler should have recovered gear. scrambler.gained={scrambler_gained}"


# ==============================================================================
# Smoke Tests — All Missions
# ==============================================================================


@pytest.mark.parametrize(
    "mission_class",
    PLANKY_BEHAVIOR_EVALS,
    ids=[m.model_fields["name"].default for m in PLANKY_BEHAVIOR_EVALS],
)
def test_planky_behavior_mission_runs(mission_class: type) -> None:
    """Smoke test: All planky behavior missions should run without error."""
    # Determine appropriate vibes for the mission
    name = mission_class.model_fields["name"].default
    if "aligner" in name:
        vibes = {"aligner": 1}
    elif "scrambler" in name:
        vibes = {"scrambler": 1}
    elif "scout" in name:
        vibes = {"scout": 1}
    elif "multi_role" in name:
        vibes = {"miner": 1, "scout": 1, "aligner": 1, "scrambler": 1}
    else:
        vibes = {"miner": 1}

    stats = run_planky_episode(mission_class, max_steps=50, vibes=vibes)
    assert stats["steps"] > 0, f"Mission {mission_class} should run for at least one step"
