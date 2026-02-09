import types

from metta.common.tool.recipe import Recipe


def test_recipe_skips_maker_when_type_hints_raise_import_error(monkeypatch):
    module = types.ModuleType("fake_recipe_module")

    def some_callable():  # pragma: no cover - should be skipped
        raise AssertionError("should not be invoked")

    module.some_callable = some_callable  # type: ignore[attr-defined]

    def _boom(_fn):
        raise ImportError("missing optional dependency")

    monkeypatch.setattr("metta.common.tool.recipe.get_type_hints", _boom)

    recipe = Recipe(module)
    assert recipe.get_all_tool_maker_names() == set()
