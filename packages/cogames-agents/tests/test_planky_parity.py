"""
Parity checks between the Python `planky` scripted policy and the Nim-backed `planky_nim`.

These are intentionally scoped to "key outcome" stats in deterministic Planky eval arenas.
We do not currently assert full per-step action equivalence: the policies may take different
paths while still achieving the same goal-tree outcomes (gear, mining, hearts, scrambles).
"""

from __future__ import annotations

from typing import Any

import pytest
from cogames_agents.evals.planky_evals import (
    PlankyAlignerHearts,
    PlankyMinerBestResource,
    PlankyMinerExtract,
    PlankyMinerGear,
    PlankyScoutExplore,
    PlankyScramblerTarget,
)

from mettagrid.policy.loader import discover_and_register_policies
from mettagrid.policy.policy import PolicySpec
from mettagrid.runner.rollout import run_episode_local

# Ensure both policies are registered.
discover_and_register_policies("cogames_agents.policy")


def _run_episode(
    policy_name: str,
    mission_class: type,
    *,
    max_steps: int,
    roles: dict[str, int],
    seed: int = 42,
) -> dict[str, Any]:
    mission = mission_class()
    env_cfg = mission.make_env()
    env_cfg.game.max_steps = max_steps

    # Explicitly set all roles so we don't rely on policy defaults.
    init_kwargs = {"miner": 0, "scout": 0, "aligner": 0, "scrambler": 0}
    init_kwargs.update(roles)

    spec = PolicySpec(class_path=policy_name, data_path=None, init_kwargs=init_kwargs)
    results, _replay = run_episode_local(
        policy_specs=[spec],
        assignments=[0] * env_cfg.game.num_agents,
        env=env_cfg,
        seed=seed,
        device="cpu",
        render_mode="none",
    )
    return {"steps": results.steps, "stats": results.stats, "rewards": results.rewards}


@pytest.mark.parametrize(
    ("mission_cls", "max_steps", "roles", "key_stats"),
    [
        (PlankyMinerGear, 100, {"miner": 1}, ["miner.gained"]),
        (PlankyMinerExtract, 200, {"miner": 1}, ["miner.gained", "carbon.gained"]),
        (PlankyMinerBestResource, 300, {"miner": 1}, ["carbon.gained", "oxygen.gained"]),
        (PlankyAlignerHearts, 200, {"aligner": 1}, ["aligner.gained", "heart.gained"]),
        (PlankyScramblerTarget, 300, {"scrambler": 1}, ["scrambler.gained", "junction.scrambled_by_agent"]),
        (PlankyScoutExplore, 200, {"scout": 1}, ["scout.gained"]),
    ],
)
def test_planky_nim_matches_planky_key_outcomes(
    mission_cls: type,
    max_steps: int,
    roles: dict[str, int],
    key_stats: list[str],
) -> None:
    py = _run_episode("planky", mission_cls, max_steps=max_steps, roles=roles)
    nim = _run_episode("planky_nim", mission_cls, max_steps=max_steps, roles=roles)

    assert py["steps"] == nim["steps"], f"Expected same step count, got planky={py['steps']} planky_nim={nim['steps']}"

    py_agent_stats = (py["stats"].get("agent") or [{}])[0]
    nim_agent_stats = (nim["stats"].get("agent") or [{}])[0]
    assert py_agent_stats and nim_agent_stats, "Expected agent stats to be present for both policies"

    for key in key_stats:
        assert py_agent_stats.get(key, 0) == nim_agent_stats.get(key, 0), (
            f"Key stat mismatch for {mission_cls.__name__}: {key} "
            f"planky={py_agent_stats.get(key, 0)} planky_nim={nim_agent_stats.get(key, 0)}"
        )
