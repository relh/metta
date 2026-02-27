from __future__ import annotations

from typing import Sequence

from pydantic import Field

from metta.cogworks.curriculum.curriculum import CurriculumAlgorithmConfig, CurriculumConfig
from metta.cogworks.curriculum.tree_curriculum import (
    MechanicsTreeDefinition,
    TreeNode,
    TreeTaskGenerator,
    build_tree_nodes,
    make_tree_curriculum_from_definition,
)
from metta.games.hunger.variants import VARIANTS

_NON_MECHANIC_VARIANTS = {"full", "multi_year_5", "multi_year_10"}


def hunger_mechanics() -> list[str]:
    return [variant.name for variant in VARIANTS if variant.name not in _NON_MECHANIC_VARIANTS]


_HUNGER_MECHANICS = tuple(hunger_mechanics())


HUNGER_MECHANICS_TREE = MechanicsTreeDefinition(
    game="hunger",
    mechanics=_HUNGER_MECHANICS,
    interface_variants=_HUNGER_MECHANICS,
    max_steps=250,
)

HungerTreeNode = TreeNode


def build_hunger_tree_nodes(
    mechanics: Sequence[str] | None = None,
    *,
    max_combination_size: int | None = None,
) -> list[HungerTreeNode]:
    selected_mechanics = mechanics if mechanics is not None else HUNGER_MECHANICS_TREE.mechanics
    return build_tree_nodes(
        game=HUNGER_MECHANICS_TREE.game,
        mechanics=selected_mechanics,
        max_combination_size=max_combination_size,
    )


class HungerTreeTaskGenerator(TreeTaskGenerator):
    class Config(TreeTaskGenerator.Config):
        game: str = "hunger"
        mechanics: list[str] = Field(default_factory=lambda: list(_HUNGER_MECHANICS))
        max_steps: int = Field(default=250, ge=1)
        # Keep interface fixed to full hunger mechanics by default.
        interface_variants: list[str] | None = Field(default_factory=lambda: list(_HUNGER_MECHANICS))


def make_hunger_tree_curriculum(
    *,
    num_agents: int = 40,
    max_steps: int = 250,
    mechanics: Sequence[str] | None = None,
    max_combination_size: int | None = None,
    max_task_id: int = 1_000_000,
    num_active_tasks: int = 64,
    algorithm_config: CurriculumAlgorithmConfig | None = None,
) -> CurriculumConfig:
    return make_tree_curriculum_from_definition(
        HUNGER_MECHANICS_TREE,
        num_agents=num_agents,
        max_steps=max_steps,
        mechanics=mechanics,
        max_combination_size=max_combination_size,
        max_task_id=max_task_id,
        num_active_tasks=num_active_tasks,
        algorithm_config=algorithm_config,
        task_generator_config_cls=HungerTreeTaskGenerator.Config,
    )
