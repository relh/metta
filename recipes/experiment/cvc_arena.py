"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from typing import Optional

import metta.cogworks.curriculum as cc
import metta.tools as tools
import mettagrid.builder.envs as eb
from metta.cogworks.curriculum.curriculum import (
    CurriculumAlgorithmConfig,
    CurriculumConfig,
)
from metta.cogworks.curriculum.learning_progress_algorithm import LearningProgressConfig
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.sim.simulation_config import SimulationConfig
from mettagrid.config import MettaGridConfig


def mettagrid(num_agents: int = 24) -> MettaGridConfig:
    arena_env = eb.make_arena(num_agents=num_agents)

    return arena_env


def make_curriculum(
    arena_env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
) -> CurriculumConfig:
    arena_env = arena_env or mettagrid()

    arena_tasks = cc.bucketed(arena_env)

    for item in ["ore_red", "battery_red", "laser", "armor"]:
        arena_tasks.add_bucket(f"game.agent.rewards.inventory.{item}", [0, 0.1, 0.5, 0.9, 1.0])
        arena_tasks.add_bucket(f"game.agent.rewards.inventory_max.{item}", [1, 2])

    # enable or disable attacks. we use cost instead of 'enabled'
    # to maintain action space consistency.
    arena_tasks.add_bucket("game.actions.attack.consumed_resources.laser", [1, 100])

    if algorithm_config is None:
        algorithm_config = LearningProgressConfig.default()

    return arena_tasks.to_curriculum(algorithm_config=algorithm_config)


def simulations(env: Optional[MettaGridConfig] = None) -> list[SimulationConfig]:
    basic_env = env or mettagrid()
    basic_env.game.actions.attack.consumed_resources["laser"] = 100

    combat_env = basic_env.model_copy()
    combat_env.game.actions.attack.consumed_resources["laser"] = 1

    return [
        SimulationConfig(suite="cvc_arena", name="basic", env=basic_env),
        SimulationConfig(suite="cvc_arena", name="combat", env=combat_env),
    ]


def train(
    curriculum: Optional[CurriculumConfig] = None,
) -> tools.TrainTool:
    resolved_curriculum = curriculum or make_curriculum()

    trainer_cfg = TrainerConfig()

    evaluator_cfg = EvaluatorConfig(
        simulations=[
            SimulationConfig(suite="cvc_arena", name="basic", env=mettagrid(num_agents=24)),
            SimulationConfig(suite="cvc_arena", name="combat", env=mettagrid(num_agents=24)),
        ],
    )

    return tools.TrainTool(
        trainer=trainer_cfg,
        training_env=TrainingEnvironmentConfig(curriculum=resolved_curriculum),
        evaluator=evaluator_cfg,
    )


def evaluate(
    policy_uris: list[str] | str,
) -> tools.EvaluateTool:
    return tools.EvaluateTool(
        simulations=simulations(),
        policy_uris=policy_uris,
    )


def play(policy_uri: Optional[str] = None) -> tools.PlayTool:
    """Interactive play with a policy."""
    return tools.PlayTool(sim=simulations()[0], policy_uri=policy_uri)


def replay(policy_uri: Optional[str] = None) -> tools.ReplayTool:
    """Generate replay from a policy."""
    return tools.ReplayTool(sim=simulations()[0], policy_uri=policy_uri)
