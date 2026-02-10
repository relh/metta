"""
Behavior smoke tests for the Nim-backed planky entrypoint (`planky_nim`).

These are intentionally minimal: they validate that the new Nim policy can run
in the deterministic Planky eval arenas and achieve at least basic capability.
"""

from __future__ import annotations

from typing import Any

import pytest
from cogames_agents.evals.planky_evals import (
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
from mettagrid.runner.rollout import run_episode_local

discover_and_register_policies("cogames_agents.policy")


def run_planky_nim_episode(
    mission_class: type,
    *,
    max_steps: int | None = None,
    roles: dict[str, int] | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    mission = mission_class()
    env_cfg = mission.make_env()
    if max_steps is not None:
        env_cfg.game.max_steps = max_steps

    init_kwargs = {"miner": 0, "scout": 0, "aligner": 0, "scrambler": 0}
    if roles:
        init_kwargs.update(roles)
    else:
        init_kwargs["miner"] = 1

    policy_spec = PolicySpec(class_path="planky_nim", data_path=None, init_kwargs=init_kwargs)
    results, _replay = run_episode_local(
        policy_specs=[policy_spec],
        assignments=[0] * env_cfg.game.num_agents,
        env=env_cfg,
        seed=seed,
        device="cpu",
        render_mode="none",
    )
    return {"steps": results.steps, "stats": results.stats, "rewards": results.rewards}


@pytest.mark.parametrize(
    ("mission_cls", "role"),
    [
        (PlankyMinerGear, "miner"),
        (PlankyScoutGear, "scout"),
        (PlankyAlignerGear, "aligner"),
        (PlankyScramblerGear, "scrambler"),
    ],
)
def test_planky_nim_role_gets_gear(mission_cls: type, role: str) -> None:
    stats = run_planky_nim_episode(mission_cls, max_steps=100, roles={role: 1})
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get(f"{role}.gained", 0) > 0, f"Expected {role} gear gain, got stats={agent_stats[0]}"


def test_planky_nim_miner_extracts_carbon() -> None:
    stats = run_planky_nim_episode(PlankyMinerExtract, max_steps=200, roles={"miner": 1})
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    carbon_gained = agent_stats[0].get("carbon.gained", 0)
    assert carbon_gained > 0, f"Expected some carbon mined, got stats={agent_stats[0]}"


def test_planky_nim_miner_picks_best_resource() -> None:
    stats = run_planky_nim_episode(PlankyMinerBestResource, max_steps=300, roles={"miner": 1})
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    carbon_gained = agent_stats[0].get("carbon.gained", 0)
    assert carbon_gained > 0, f"Expected miner to mine carbon in best-resource arena, got stats={agent_stats[0]}"


def test_planky_nim_miner_deposits_cargo() -> None:
    stats = run_planky_nim_episode(PlankyMinerDeposit, max_steps=200, roles={"miner": 1})
    assert stats["steps"] > 0


def test_planky_nim_miner_full_cycle() -> None:
    stats = run_planky_nim_episode(PlankyMinerFullCycle, max_steps=400, roles={"miner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("carbon.gained", 0) > 0, f"Expected some carbon mined, got stats={agent_stats[0]}"


def test_planky_nim_aligner_gets_hearts() -> None:
    stats = run_planky_nim_episode(PlankyAlignerHearts, max_steps=200, roles={"aligner": 1})
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("heart.gained", 0) > 0, f"Expected some hearts gained, got stats={agent_stats[0]}"


def test_planky_nim_aligner_approaches_junction() -> None:
    stats = run_planky_nim_episode(PlankyAlignerJunction, max_steps=300, roles={"aligner": 1})
    assert stats["steps"] > 0


def test_planky_nim_aligner_avoids_enemy_aoe() -> None:
    stats = run_planky_nim_episode(PlankyAlignerAvoidAOE, max_steps=400, roles={"aligner": 1})
    assert stats["steps"] > 0


def test_planky_nim_scrambler_scrambles_junction() -> None:
    stats = run_planky_nim_episode(PlankyScramblerTarget, max_steps=300, roles={"scrambler": 1})
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("junction.scrambled_by_agent", 0) > 0, (
        f"Expected scrambler to scramble a junction, got stats={agent_stats[0]}"
    )


def test_planky_nim_scout_explores() -> None:
    stats = run_planky_nim_episode(PlankyScoutExplore, max_steps=200, roles={"scout": 1})
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("action.move.success", 0) > 50, (
        f"Expected scout to move around, got stats={agent_stats[0]}"
    )


def test_planky_nim_survive_retreat() -> None:
    stats = run_planky_nim_episode(PlankySurviveRetreat, max_steps=200, roles={"miner": 1})
    assert stats["steps"] > 0


def test_planky_nim_maze_navigation_mines_carbon() -> None:
    stats = run_planky_nim_episode(PlankyMaze, max_steps=400, roles={"miner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("carbon.gained", 0) > 0, f"Expected some carbon mined, got stats={agent_stats[0]}"


def test_planky_nim_distant_exploration_mines_carbon() -> None:
    stats = run_planky_nim_episode(PlankyExplorationDistant, max_steps=400, roles={"miner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("carbon.gained", 0) > 0, f"Expected some carbon mined, got stats={agent_stats[0]}"


def test_planky_nim_stuck_corridor_mines_carbon() -> None:
    stats = run_planky_nim_episode(PlankyStuckCorridor, max_steps=400, roles={"miner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("carbon.gained", 0) > 0, f"Expected some carbon mined, got stats={agent_stats[0]}"


def test_planky_nim_multi_role() -> None:
    stats = run_planky_nim_episode(
        PlankyMultiRole,
        max_steps=300,
        roles={"miner": 1, "scout": 1, "aligner": 1, "scrambler": 1},
    )
    assert stats["steps"] > 0


def test_planky_nim_aligner_full_cycle() -> None:
    stats = run_planky_nim_episode(PlankyAlignerFullCycle, max_steps=400, roles={"aligner": 1})
    assert stats["steps"] > 0


def test_planky_nim_scrambler_full_cycle() -> None:
    stats = run_planky_nim_episode(PlankyScramblerFullCycle, max_steps=400, roles={"scrambler": 1})
    assert stats["steps"] > 0


def test_planky_nim_resource_chain_mines_resources() -> None:
    stats = run_planky_nim_episode(PlankyResourceChain, max_steps=500, roles={"miner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    resources_gained = sum(agent_stats[0].get(f"{r}.gained", 0) for r in ("carbon", "oxygen", "germanium", "silicon"))
    assert resources_gained > 0, f"Expected some resources mined, got stats={agent_stats[0]}"


def test_planky_nim_miner_re_gears() -> None:
    stats = run_planky_nim_episode(PlankyMinerReGear, max_steps=300, roles={"miner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("miner.gained", 0) > 0, f"Expected miner to re-gear, got stats={agent_stats[0]}"
    assert agent_stats[0].get("carbon.gained", 0) > 0, (
        f"Expected miner to mine after re-gearing, got stats={agent_stats[0]}"
    )


def test_planky_nim_aligner_re_gears() -> None:
    stats = run_planky_nim_episode(PlankyAlignerReGear, max_steps=400, roles={"aligner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("aligner.gained", 0) > 0, f"Expected aligner to re-gear, got stats={agent_stats[0]}"


def test_planky_nim_aligner_re_hearts() -> None:
    stats = run_planky_nim_episode(PlankyAlignerReHearts, max_steps=400, roles={"aligner": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("heart.gained", 0) > 0, (
        f"Expected aligner to re-acquire hearts, got stats={agent_stats[0]}"
    )


def test_planky_nim_scrambler_recovers() -> None:
    stats = run_planky_nim_episode(PlankyScramblerRecovery, max_steps=400, roles={"scrambler": 1})
    assert stats["steps"] > 0
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    assert agent_stats[0].get("scrambler.gained", 0) > 0, (
        f"Expected scrambler to recover gear, got stats={agent_stats[0]}"
    )


@pytest.mark.parametrize("mission_cls", [PlankyMaze, PlankyStuckCorridor])
def test_planky_nim_does_not_get_stuck_in_nav_arenas(mission_cls: type) -> None:
    stats = run_planky_nim_episode(mission_cls, max_steps=200, roles={"miner": 1})
    agent_stats = stats["stats"].get("agent", [])
    assert agent_stats, "Expected agent stats to be present"
    # Regression guard for nav cache/stuck handling. If the agent is thrashing, this spikes.
    assert agent_stats[0].get("status.max_steps_without_motion", 999) < 25, (
        f"Expected agent to avoid long stuck periods, got stats={agent_stats[0]}"
    )


# ==============================================================================
# Smoke Tests — All Missions (Integration Parity With Python Planky)
# ==============================================================================


@pytest.mark.parametrize(
    "mission_class",
    PLANKY_BEHAVIOR_EVALS,
    ids=[m.model_fields["name"].default for m in PLANKY_BEHAVIOR_EVALS],
)
def test_planky_nim_behavior_mission_runs(mission_class: type) -> None:
    """Smoke test: All Planky behavior missions should run under planky_nim without error."""
    name = mission_class.model_fields["name"].default
    if "aligner" in name:
        roles = {"aligner": 1}
    elif "scrambler" in name:
        roles = {"scrambler": 1}
    elif "scout" in name:
        roles = {"scout": 1}
    elif "multi_role" in name:
        roles = {"miner": 1, "scout": 1, "aligner": 1, "scrambler": 1}
    else:
        roles = {"miner": 1}

    stats = run_planky_nim_episode(mission_class, max_steps=50, roles=roles)
    assert stats["steps"] > 0, f"Mission {mission_class} should run for at least one step"
