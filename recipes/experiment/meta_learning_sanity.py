from __future__ import annotations

from typing import Literal

import metta.cogworks.curriculum as cc
import metta.tools as tools
import mettagrid.builder.envs as eb
from metta.cogworks.curriculum import CurriculumConfig
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.sim.simulation_config import SimulationConfig
from mettagrid.config.mettagrid_config import MettaGridConfig
from mettagrid.config.reward_config import inventoryReward

TaskName = Literal["collect_ore_red", "collect_battery_red"]


def _task_env(
    task: TaskName,
    *,
    num_agents: int = 4,
    goal_obs: bool = True,
    observe_last_reward: bool = True,
    max_steps: int = 300,
) -> MettaGridConfig:
    """Create a single-task env.

    The only difference between tasks is which inventory item is rewarded. The intent is
    to validate that task-conditioning signals (e.g. `goal_obs` or `last_reward`) allow
    a single policy to adapt across tasks.
    """
    env = eb.make_arena(num_agents=num_agents, combat=False)
    env.game.max_steps = max_steps

    env.game.obs.global_obs.goal_obs = goal_obs
    env.game.obs.global_obs.last_reward = observe_last_reward

    ore_weight = 1.0 if task == "collect_ore_red" else 0.0
    battery_weight = 1.0 if task == "collect_battery_red" else 0.0

    env.label = task
    env.game.agent.rewards = {
        "ore_red": inventoryReward("ore_red", weight=ore_weight, max=1),
        "battery_red": inventoryReward("battery_red", weight=battery_weight, max=1),
    }

    return env


def curriculum(
    *,
    num_agents: int = 4,
    goal_obs: bool = True,
    observe_last_reward: bool = True,
    max_steps: int = 300,
) -> CurriculumConfig:
    """Two-task curriculum used by the sanity-check recipe.

    Notes:
    - We intentionally use a tiny task-id range and `num_active_tasks=2` so the
      curriculum pool is exactly two tasks.
    - We keep `algorithm_config=None` so the pool is stable (no evictions that would
      deadlock with a tiny `max_task_id`).
    """
    ore_env = _task_env(
        "collect_ore_red",
        num_agents=num_agents,
        goal_obs=goal_obs,
        observe_last_reward=observe_last_reward,
        max_steps=max_steps,
    )
    battery_env = _task_env(
        "collect_battery_red",
        num_agents=num_agents,
        goal_obs=goal_obs,
        observe_last_reward=observe_last_reward,
        max_steps=max_steps,
    )

    task_generator = cc.CyclicTaskGeneratorSet.Config(
        task_generators=[
            cc.SingleTaskGenerator.Config(env=ore_env),
            cc.SingleTaskGenerator.Config(env=battery_env),
        ],
    )

    return CurriculumConfig(
        task_generator=task_generator,
        # Inclusive upper bound. We want task IDs {0, 1} so that a 2-generator
        # CyclicTaskGeneratorSet never wraps and maps both active tasks to the same generator.
        max_task_id=1,
        num_active_tasks=2,
        algorithm_config=None,
    )


def simulations(
    *,
    num_agents: int = 4,
    goal_obs: bool = True,
    observe_last_reward: bool = True,
    max_steps: int = 300,
) -> list[SimulationConfig]:
    return [
        SimulationConfig(
            suite="meta_learning_sanity",
            name="collect_ore_red",
            env=_task_env(
                "collect_ore_red",
                num_agents=num_agents,
                goal_obs=goal_obs,
                observe_last_reward=observe_last_reward,
                max_steps=max_steps,
            ),
        ),
        SimulationConfig(
            suite="meta_learning_sanity",
            name="collect_battery_red",
            env=_task_env(
                "collect_battery_red",
                num_agents=num_agents,
                goal_obs=goal_obs,
                observe_last_reward=observe_last_reward,
                max_steps=max_steps,
            ),
        ),
    ]


def train(
    *,
    num_agents: int = 4,
    goal_obs: bool = True,
    observe_last_reward: bool = True,
    max_steps: int = 300,
) -> tools.TrainTool:
    """Train across two tasks and evaluate on each task separately.

    Suggested usage:
    - With goal observation tokens (explicit task signal):
      `uv run ./tools/run.py recipes.experiment.meta_learning_sanity.train goal_obs=true`
    - Without goal observation tokens (harder; relies on within-episode trial-and-error):
      `uv run ./tools/run.py recipes.experiment.meta_learning_sanity.train goal_obs=false`
    """
    return tools.TrainTool(
        training_env=TrainingEnvironmentConfig(
            curriculum=curriculum(
                num_agents=num_agents,
                goal_obs=goal_obs,
                observe_last_reward=observe_last_reward,
                max_steps=max_steps,
            )
        ),
        evaluator=EvaluatorConfig(
            simulations=simulations(
                num_agents=num_agents,
                goal_obs=goal_obs,
                observe_last_reward=observe_last_reward,
                max_steps=max_steps,
            ),
        ),
    )
