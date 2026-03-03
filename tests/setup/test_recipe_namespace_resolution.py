from __future__ import annotations

import pytest

from metta.common.tool.recipe_registry import recipe_registry
from metta.common.tool.tool_path import resolve_and_load_tool_maker

pytestmark = pytest.mark.setup


def test_short_hunger_recipe_resolves_to_canonical_namespace() -> None:
    recipe_registry.clear()
    try:
        recipe = recipe_registry.get("hunger")
        assert recipe is not None
        assert recipe.module_name == "recipes.game.hunger"
        assert recipe.short_name == "hunger"
    finally:
        recipe_registry.clear()


def test_short_cogsguard_train_tool_path_prefers_canonical_namespace() -> None:
    recipe_registry.clear()
    try:
        maker = resolve_and_load_tool_maker("cogsguard.train")
        assert maker is not None
        assert maker.__module__ == "recipes.game.cogsguard"
        assert maker.__name__ == "train"
    finally:
        recipe_registry.clear()


def test_short_cogs_vs_clips_train_tool_path_prefers_canonical_namespace() -> None:
    recipe_registry.clear()
    try:
        maker = resolve_and_load_tool_maker("cogs_vs_clips.train")
        assert maker is not None
        assert maker.__module__ == "recipes.game.cogs_vs_clips"
        assert maker.__name__ == "train"
    finally:
        recipe_registry.clear()


def test_short_name_recipe_lookup_prefers_game_then_prod_then_experiment() -> None:
    game_recipe = object()
    prod_recipe = object()
    experiment_recipe = object()

    recipe_registry.clear()
    try:
        recipe_registry.path_to_recipe = {
            "recipes.game.foo": game_recipe,
            "recipes.prod.foo": prod_recipe,
            "recipes.experiment.foo": experiment_recipe,
        }
        recipe_registry._discovered = True

        for key_to_remove, expected_recipe in (
            ("recipes.game.foo", game_recipe),
            ("recipes.prod.foo", prod_recipe),
            ("recipes.experiment.foo", experiment_recipe),
        ):
            assert recipe_registry.get("foo") is expected_recipe
            recipe_registry.path_to_recipe.pop(key_to_remove, None)
    finally:
        recipe_registry.clear()
