from __future__ import annotations

from metta.cogworks.curriculum import Curriculum
from mettagrid.config.reward_config import AgentReward
from mettagrid.simulator import Simulation
from recipes.experiment import arena


def test_arena_curriculum_task_rewards_are_typed() -> None:
    curriculum = Curriculum(arena.make_curriculum(), seed=0)

    for _ in range(5):
        env_cfg = curriculum.get_task().get_env_cfg()
        for item in ("ore_red", "battery_red", "laser", "armor"):
            assert isinstance(env_cfg.game.agent.rewards[item], AgentReward)


def test_arena_curriculum_task_builds_simulation() -> None:
    curriculum = Curriculum(arena.make_curriculum(), seed=0)
    env_cfg = curriculum.get_task().get_env_cfg()

    sim = Simulation(env_cfg)
    assert sim.num_agents == env_cfg.game.num_agents


def test_train_shaped_rewards_false_is_heart_only() -> None:
    tool = arena.train_shaped(rewards=False)
    env_cfg = Curriculum(tool.training_env.curriculum, seed=0).get_task().get_env_cfg()

    assert set(env_cfg.game.agent.rewards) == {"heart"}


def test_train_shaped_rewards_true_includes_shaping_rewards() -> None:
    tool = arena.train_shaped(rewards=True)
    env_cfg = Curriculum(tool.training_env.curriculum, seed=0).get_task().get_env_cfg()

    assert {"heart", "ore_red", "battery_red", "laser", "armor", "blueprint"} <= set(env_cfg.game.agent.rewards)
