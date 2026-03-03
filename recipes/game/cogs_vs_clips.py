"""Canonical Cogs vs Clips recipe backed by tournament game namespaces."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import metta.cogworks.curriculum as cc
import metta.tools as tools
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.sim.simulation_config import SimulationConfig
from mettagrid.config.mettagrid_config import MettaGridConfig

DEFAULT_ENV_NAME = "cogsguard_8agents"


class _TournamentGame(Protocol):
    num_agents: int

    def generate(self, seed: int) -> MettaGridConfig: ...


def _tournament_game_registry() -> dict[str, _TournamentGame]:
    try:
        from metta.app_backend.tournament.referees.envs import GAME_REGISTRY  # noqa: PLC0415
    except ModuleNotFoundError:
        return {}
    return GAME_REGISTRY


def _resolve_tournament_game(name: str) -> _TournamentGame | None:
    return _tournament_game_registry().get(name)


def _parse_variants(variants: Sequence[str] | None) -> list[str]:
    if isinstance(variants, str):
        return [value.strip() for value in variants.split(",") if value.strip()]
    return list(variants) if variants else []


def _build_env(
    env_name: str,
    *,
    num_agents: int | None,
    cogs: int | None,
    max_steps: int | None,
    variants: list[str],
) -> MettaGridConfig:
    tournament_game = _resolve_tournament_game(env_name)
    if tournament_game is None:
        available = sorted(_tournament_game_registry())
        raise ValueError(f"Unknown tournament game {env_name!r}. Available: {available}")
    if variants:
        raise ValueError(
            f"Tournament game {env_name!r} does not support variants overrides; variants are encoded in the env name."
        )
    requested_num_agents = cogs if cogs is not None else num_agents
    if requested_num_agents is not None and requested_num_agents != tournament_game.num_agents:
        raise ValueError(
            "Tournament game "
            f"{env_name!r} has fixed num_agents={tournament_game.num_agents}, got num_agents={requested_num_agents}"
        )

    env = tournament_game.generate(seed=0)
    if max_steps is not None:
        env.game.max_steps = max_steps
    return env


def play(
    policy_uri: str | None = None,
    env_name: str = DEFAULT_ENV_NAME,
    num_agents: int | None = None,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.PlayTool:
    env = _build_env(
        env_name,
        num_agents=num_agents,
        cogs=cogs,
        max_steps=max_steps,
        variants=_parse_variants(variants),
    )
    sim = SimulationConfig(suite=env_name, name="basic", env=env)
    steps = max_steps if max_steps is not None else env.game.max_steps
    return tools.PlayTool(sim=sim, policy_uri=policy_uri, max_steps=steps)


def train(
    env_name: str = DEFAULT_ENV_NAME,
    num_agents: int | None = None,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.TrainTool:
    env = _build_env(
        env_name,
        num_agents=num_agents,
        cogs=cogs,
        max_steps=max_steps,
        variants=_parse_variants(variants),
    )
    curriculum = cc.env_curriculum(env)
    eval_sims = [SimulationConfig(suite=env_name, name="basic", env=env.model_copy(deep=True))]
    return tools.TrainTool(
        training_env=TrainingEnvironmentConfig(curriculum=curriculum),
        evaluator=EvaluatorConfig(simulations=eval_sims),
    )
