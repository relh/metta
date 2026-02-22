from __future__ import annotations

from importlib import import_module

import pytest

from metta.cogworks.curriculum import Curriculum
from mettagrid.config.reward_config import AgentReward
from mettagrid.simulator import Simulation

CURRICULUM_FACTORIES: list[tuple[str, str]] = [
    ("recipes.experiment.cvc_arena", "make_curriculum"),
    ("recipes.experiment.simple_architecture_search.basic", "make_curriculum"),
    ("recipes.experiment.abes.kickstart.checked", "make_curriculum"),
    ("recipes.experiment.abes.quantile", "make_curriculum"),
    ("recipes.experiment.abes.kickstart.cortex_100m", "make_curriculum"),
    ("recipes.experiment.arena_with_sparse_rewards", "make_curriculum"),
    ("recipes.experiment.regret_examples", "make_prioritized_regret_curriculum"),
]

ENV_FACTORIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("recipes.experiment.cvc_arena", "mettagrid", ("ore_red", "battery_red", "laser", "armor")),
    (
        "recipes.experiment.simple_architecture_search.basic",
        "mettagrid",
        ("heart", "ore_red", "battery_red", "laser", "armor", "blueprint"),
    ),
    (
        "recipes.experiment.abes.kickstart.checked",
        "mettagrid",
        ("heart", "ore_red", "battery_red", "laser", "armor", "blueprint"),
    ),
    (
        "recipes.experiment.abes.quantile",
        "mettagrid",
        ("heart", "ore_red", "battery_red", "laser", "armor", "blueprint"),
    ),
    (
        "recipes.experiment.abes.kickstart.cortex_100m",
        "mettagrid",
        ("heart", "ore_red", "battery_red", "laser", "armor", "blueprint"),
    ),
    (
        "recipes.experiment.arena_with_sparse_rewards",
        "mettagrid",
        ("heart", "ore_red", "battery_red", "laser", "armor", "blueprint"),
    ),
    ("recipes.experiment.regret_examples", "make_arena_env", ("heart", "ore_red", "battery_red", "laser", "armor")),
]


@pytest.mark.parametrize(("module_name", "curriculum_factory"), CURRICULUM_FACTORIES)
def test_recipe_curriculum_tasks_build_simulation(module_name: str, curriculum_factory: str) -> None:
    module = import_module(module_name)
    curriculum_cfg = getattr(module, curriculum_factory)()
    env_cfg = Curriculum(curriculum_cfg, seed=0).get_task().get_env_cfg()

    sim = Simulation(env_cfg)
    assert sim.num_agents == env_cfg.game.num_agents


@pytest.mark.parametrize(("module_name", "env_factory", "reward_keys"), ENV_FACTORIES)
def test_recipe_environment_rewards_are_typed(
    module_name: str,
    env_factory: str,
    reward_keys: tuple[str, ...],
) -> None:
    module = import_module(module_name)
    env_cfg = getattr(module, env_factory)()
    rewards = env_cfg.game.agent.rewards

    for key in reward_keys:
        assert isinstance(rewards[key], AgentReward)
    assert all(not key.startswith("inventory.") for key in rewards)
    assert all(not key.startswith("inventory_max.") for key in rewards)
