from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from pydantic import Field

from metta.cogworks.curriculum.curriculum import CurriculumAlgorithmConfig, CurriculumConfig
from metta.cogworks.curriculum.learning_progress_algorithm import LearningProgressConfig
from metta.cogworks.curriculum.task_generator import TaskGenerator, TaskGeneratorConfig
from metta.games.games import GAMES, make_game
from mettagrid.config.mettagrid_config import MettaGridConfig


@dataclass(frozen=True, slots=True)
class TreeNode:
    mechanics: tuple[str, ...]
    variants: tuple[str, ...]
    depth: int


@dataclass(frozen=True, slots=True)
class MechanicsTreeDefinition:
    game: str
    mechanics: tuple[str, ...]
    interface_variants: tuple[str, ...]
    max_steps: int = 250


def _variant_closure(*, game: str, variant_names: Sequence[str]) -> tuple[str, ...]:
    game_info = GAMES.get(game)
    if game_info is None:
        raise ValueError(f"Unknown game {game!r}. Available: {list(GAMES.keys())}")
    parse_variants = game_info.get("parse_variants")
    if parse_variants is None:
        return tuple(dict.fromkeys(variant_names))
    return tuple(variant.name for variant in parse_variants(list(variant_names)))


def build_tree_nodes(
    *,
    game: str,
    mechanics: Sequence[str],
    max_combination_size: int | None = None,
) -> list[TreeNode]:
    base_mechanics = list(dict.fromkeys(mechanics))
    if not base_mechanics:
        raise ValueError("Tree mechanics list cannot be empty")

    max_size = len(base_mechanics) if max_combination_size is None else min(len(base_mechanics), max_combination_size)
    if max_size < 1:
        raise ValueError("max_combination_size must be at least 1")

    nodes_by_closure: dict[tuple[str, ...], TreeNode] = {}
    for depth in range(1, max_size + 1):
        for combo in combinations(base_mechanics, depth):
            closure = _variant_closure(game=game, variant_names=combo)
            if closure not in nodes_by_closure:
                nodes_by_closure[closure] = TreeNode(
                    mechanics=tuple(combo),
                    variants=closure,
                    depth=depth,
                )

    return sorted(nodes_by_closure.values(), key=lambda node: (node.depth, len(node.variants), node.variants))


def _scope_to_interface(task_env: MettaGridConfig, interface_env: MettaGridConfig) -> MettaGridConfig:
    scoped = task_env.model_copy(deep=True)
    scoped.game.resource_names = list(dict.fromkeys([*interface_env.game.resource_names, *scoped.game.resource_names]))
    scoped.game.tags = list(dict.fromkeys([*interface_env.game.tags, *scoped.game.tags]))
    for name, object_cfg in interface_env.game.objects.items():
        if name not in scoped.game.objects:
            scoped.game.objects[name] = object_cfg.model_copy(deep=True)
    return scoped


class TreeTaskGenerator(TaskGenerator):
    class Config(TaskGeneratorConfig["TreeTaskGenerator"]):
        game: str = Field(description="Registered game name")
        num_agents: int = Field(default=40, ge=1)
        max_steps: int = Field(default=250, ge=1)
        mechanics: list[str] = Field(min_length=1, description="Base mechanics/variants that define the tree")
        max_combination_size: int | None = Field(default=None, ge=1)
        interface_variants: list[str] | None = Field(
            default=None,
            description="Variants used to define the stable interface scope; defaults to mechanics.",
        )

    def __init__(self, config: "TreeTaskGenerator.Config"):
        super().__init__(config)
        self._config = config
        self._nodes = build_tree_nodes(
            game=config.game,
            mechanics=config.mechanics,
            max_combination_size=config.max_combination_size,
        )

        interface_variants = config.interface_variants or config.mechanics
        self._interface_env = make_game(
            config.game,
            num_agents=config.num_agents,
            max_steps=config.max_steps,
            variants=interface_variants,
        )
        self._node_weights = [1.0 / float(node.depth) for node in self._nodes]

    def _generate_task(self, task_id: int, rng: random.Random) -> MettaGridConfig:
        node = rng.choices(self._nodes, weights=self._node_weights, k=1)[0]
        env = make_game(
            self._config.game,
            num_agents=self._config.num_agents,
            max_steps=self._config.max_steps,
            variants=node.variants,
        )
        scoped = _scope_to_interface(env, self._interface_env)
        scoped.label = f"{scoped.label}.tree_depth_{node.depth}"
        self._last_bucket_values = {
            "tree_depth": float(node.depth),
            "num_mechanics": float(len(node.mechanics)),
        }
        return scoped


def make_tree_curriculum(
    *,
    game: str,
    mechanics: Sequence[str],
    num_agents: int = 40,
    max_steps: int = 250,
    interface_variants: Sequence[str] | None = None,
    max_combination_size: int | None = None,
    max_task_id: int = 1_000_000,
    num_active_tasks: int = 64,
    algorithm_config: CurriculumAlgorithmConfig | None = None,
    task_generator_config_cls: type[TreeTaskGenerator.Config] = TreeTaskGenerator.Config,
) -> CurriculumConfig:
    config = task_generator_config_cls(
        game=game,
        num_agents=num_agents,
        max_steps=max_steps,
        mechanics=list(mechanics),
        interface_variants=list(interface_variants) if interface_variants is not None else None,
        max_combination_size=max_combination_size,
    )
    algorithm = algorithm_config or LearningProgressConfig.default()
    return CurriculumConfig(
        task_generator=config,
        max_task_id=max_task_id,
        num_active_tasks=num_active_tasks,
        algorithm_config=algorithm,
    )


def make_tree_curriculum_from_definition(
    definition: MechanicsTreeDefinition,
    *,
    num_agents: int = 40,
    max_steps: int | None = None,
    mechanics: Sequence[str] | None = None,
    interface_variants: Sequence[str] | None = None,
    max_combination_size: int | None = None,
    max_task_id: int = 1_000_000,
    num_active_tasks: int = 64,
    algorithm_config: CurriculumAlgorithmConfig | None = None,
    task_generator_config_cls: type[TreeTaskGenerator.Config] = TreeTaskGenerator.Config,
) -> CurriculumConfig:
    return make_tree_curriculum(
        game=definition.game,
        mechanics=mechanics if mechanics is not None else definition.mechanics,
        interface_variants=interface_variants if interface_variants is not None else definition.interface_variants,
        num_agents=num_agents,
        max_steps=definition.max_steps if max_steps is None else max_steps,
        max_combination_size=max_combination_size,
        max_task_id=max_task_id,
        num_active_tasks=num_active_tasks,
        algorithm_config=algorithm_config,
        task_generator_config_cls=task_generator_config_cls,
    )
