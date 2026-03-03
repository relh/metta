"""Canonical Hunger game recipe."""

from __future__ import annotations

from collections.abc import Sequence

import metta.tools as tools
from metta.games.games import GAMES, make_game
from metta.games.hunger.tree_curriculum import hunger_mechanics, make_hunger_tree_curriculum
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.sim.simulation_config import SimulationConfig
from mettagrid.policy.loader import discover_and_register_policies

DEFAULT_NUM_AGENTS = 40
DEFAULT_MAX_TRAIN_STEPS = 250


def _parse_variants(variants: Sequence[str] | None) -> list[str]:
    if isinstance(variants, str):
        return [value.strip() for value in variants.split(",") if value.strip()]
    return list(variants) if variants else []


def _resolve_num_agents(num_agents: int | None, cogs: int | None) -> int:
    if cogs is not None:
        return cogs
    if num_agents is not None:
        return num_agents
    return DEFAULT_NUM_AGENTS


def play(
    policy_uri: str | None = None,
    num_agents: int | None = None,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.PlayTool:
    info = GAMES["hunger"]
    if policy_uri is None:
        policy_uri = info["policy_uri"]
    for package_name in info["policy_packages"]:
        discover_and_register_policies(package_name)

    effective_num_agents = _resolve_num_agents(num_agents, cogs)
    variant_list = _parse_variants(variants)
    env = make_game(
        "hunger",
        num_agents=effective_num_agents,
        max_steps=max_steps,
        variants=variant_list if variant_list else None,
    )
    sim = SimulationConfig(suite="hunger", name="basic", env=env)
    steps = max_steps if max_steps is not None else env.game.max_steps
    return tools.PlayTool(sim=sim, policy_uri=policy_uri, max_steps=steps)


def train(
    num_agents: int | None = None,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.TrainTool:
    effective_num_agents = _resolve_num_agents(num_agents, cogs)
    variant_list = _parse_variants(variants)
    steps = max_steps if max_steps is not None else DEFAULT_MAX_TRAIN_STEPS

    mechanics = variant_list if variant_list else hunger_mechanics()
    curriculum = make_hunger_tree_curriculum(
        num_agents=effective_num_agents,
        max_steps=steps,
        mechanics=mechanics,
    )
    eval_env = make_game(
        "hunger",
        num_agents=effective_num_agents,
        max_steps=steps,
        variants=hunger_mechanics(),
    )
    eval_sims = [SimulationConfig(suite="hunger", name="full_mechanics", env=eval_env)]

    return tools.TrainTool(
        training_env=TrainingEnvironmentConfig(curriculum=curriculum),
        evaluator=EvaluatorConfig(simulations=eval_sims),
    )
