"""Generic game recipe for registered games."""

from __future__ import annotations

from typing import Sequence

import metta.cogworks.curriculum as cc
import metta.tools as tools
from metta.games.games import GAMES, make_game
from metta.games.hunger.tree_curriculum import hunger_mechanics, make_hunger_tree_curriculum
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.sim.simulation_config import SimulationConfig
from mettagrid.policy.loader import discover_and_register_policies


def _parse_variants(variants: Sequence[str] | None) -> list[str]:
    if isinstance(variants, str):
        return [value.strip() for value in variants.split(",") if value.strip()]
    return list(variants) if variants else []


def play(
    game: str = "hunger",
    policy_uri: str | None = None,
    num_agents: int = 40,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.PlayTool:
    if game not in GAMES:
        raise ValueError(f"Unknown game {game!r}. Available: {list(GAMES.keys())}")

    info = GAMES[game]
    if policy_uri is None:
        policy_uri = info.get("policy_uri")
    for pkg in info.get("policy_packages", []):
        discover_and_register_policies(pkg)

    variant_list = _parse_variants(variants)
    env = make_game(
        game,
        num_agents=num_agents,
        cogs=cogs,
        max_steps=max_steps,
        variants=variant_list if variant_list else None,
    )
    sim = SimulationConfig(suite=game, name="basic", env=env)
    steps = max_steps if max_steps is not None else env.game.max_steps
    return tools.PlayTool(sim=sim, policy_uri=policy_uri, max_steps=steps)


def train(
    game: str = "hunger",
    num_agents: int = 40,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.TrainTool:
    if game not in GAMES:
        raise ValueError(f"Unknown game {game!r}. Available: {list(GAMES.keys())}")

    effective_num_agents = cogs if cogs is not None else num_agents
    variant_list = _parse_variants(variants)
    steps = max_steps if max_steps is not None else 250

    if game == "hunger":
        mechanics = variant_list if variant_list else hunger_mechanics()
        curriculum = make_hunger_tree_curriculum(
            num_agents=effective_num_agents,
            max_steps=steps,
            mechanics=mechanics,
        )
        eval_env = make_game(
            game,
            num_agents=effective_num_agents,
            max_steps=steps,
            variants=hunger_mechanics(),
        )
        eval_sims = [SimulationConfig(suite=game, name="full_mechanics", env=eval_env)]
    else:
        env = make_game(
            game,
            num_agents=effective_num_agents,
            max_steps=steps,
            variants=variant_list if variant_list else None,
        )
        curriculum = cc.env_curriculum(env)
        eval_sims = [SimulationConfig(suite=game, name="basic", env=env.model_copy(deep=True))]

    return tools.TrainTool(
        training_env=TrainingEnvironmentConfig(curriculum=curriculum),
        evaluator=EvaluatorConfig(simulations=eval_sims),
    )
