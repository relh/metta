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
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.sim.simulation_config import SimulationConfig
from mettagrid import MettaGridConfig
from mettagrid.config.reward_config import inventoryReward

# TODO(dehydration): make sure this trains as well as main on arena
# it's possible the maps are now different


def mettagrid(num_agents: int = 24) -> MettaGridConfig:
    arena_env = eb.make_arena(num_agents=num_agents)
    arena_env.game.agent.rewards.update(
        {
            "ore_red": inventoryReward("ore_red", weight=0.1, max=2),
            "battery_red": inventoryReward("battery_red", weight=0, max=1),
            "laser": inventoryReward("laser", weight=0.9, max=2),
            "armor": inventoryReward("armor", weight=0.5, max=2),
        }
    )
    return arena_env


def make_curriculum(
    arena_env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
) -> CurriculumConfig:
    arena_env = arena_env or mettagrid()

    arena_tasks = cc.bucketed(arena_env)

    # arena_tasks.add_bucket("game.map_builder.instance.params.agents", [1, 2, 3, 4, 6])
    # arena_tasks.add_bucket("game.map_builder.width", [10, 20, 30, 40])
    # arena_tasks.add_bucket("game.map_builder.height", [10, 20, 30, 40])
    # arena_tasks.add_bucket("game.map_builder.instance_border_width", [0, 6])

    for item in ["ore_red", "battery_red", "laser", "armor"]:
        arena_tasks.add_bucket(f"game.agent.rewards.{item}.weight", [0, 0.1, 0.5, 0.9, 1.0])

    # enable or disable attacks. we use cost instead of 'enabled'
    # to maintain action space consistency.
    arena_tasks.add_bucket("game.actions.attack.consumed_resources.laser", [1, 100])
    arena_tasks.add_bucket("game.agent.inventory.initial.ore_red", [0, 1, 3])
    arena_tasks.add_bucket("game.agent.inventory.initial.battery_red", [0, 3])

    if algorithm_config is None:
        algorithm_config = LearningProgressConfig.default()

    return arena_tasks.to_curriculum(algorithm_config=algorithm_config)


def simulations(env: Optional[MettaGridConfig] = None) -> list[SimulationConfig]:
    basic_env = env or mettagrid()
    basic_env.game.actions.attack.consumed_resources["laser"] = 100

    combat_env = basic_env.model_copy()
    combat_env.game.actions.attack.consumed_resources["laser"] = 1

    return [
        SimulationConfig(suite="arena", name="basic", env=basic_env),
        SimulationConfig(suite="arena", name="combat", env=combat_env),
    ]


def train(
    curriculum: Optional[CurriculumConfig] = None,
) -> tools.TrainTool:
    curriculum = curriculum or make_curriculum()

    return tools.TrainTool(
        training_env=TrainingEnvironmentConfig(curriculum=curriculum),
        evaluator=EvaluatorConfig(
            simulations=simulations(),
        ),
    )


def train_shaped(rewards: bool = True) -> tools.TrainTool:
    env_cfg = mettagrid()
    # Keep rewards=False behavior as heart-only for ablation experiments.
    env_cfg.game.agent.rewards = {"heart": inventoryReward("heart", weight=1, max=100)}

    if rewards:
        env_cfg.game.agent.rewards.update(
            {
                "ore_red": inventoryReward("ore_red", weight=0.1, max=1),
                "battery_red": inventoryReward("battery_red", weight=0.8, max=1),
                "laser": inventoryReward("laser", weight=0.5, max=1),
                "armor": inventoryReward("armor", weight=0.5, max=1),
                "blueprint": inventoryReward("blueprint", weight=0.5, max=1),
            }
        )

    return tools.TrainTool(
        training_env=TrainingEnvironmentConfig(curriculum=cc.env_curriculum(env_cfg)),
        evaluator=EvaluatorConfig(simulations=simulations()),
    )


def evaluate(
    policy_uris: list[str] | str,
) -> tools.EvaluateTool:
    if isinstance(policy_uris, str):
        policy_uris = [policy_uris]
    return tools.EvaluateTool(
        simulations=simulations(),
        policy_uris=policy_uris,
    )


def replay(policy_uri: Optional[str] = None) -> tools.ReplayTool:
    return tools.ReplayTool(sim=simulations()[0], policy_uri=policy_uri)


def play(policy_uri: Optional[str] = None) -> tools.PlayTool:
    return tools.PlayTool(sim=simulations()[0], policy_uri=policy_uri)
