"""Recipe registry for discovering and caching recipe modules."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil

from metta.common.tool.recipe import Recipe

RECIPE_SEARCH_PREFIXES: tuple[str, ...] = (
    "recipes.game",
    "recipes.prod",
    "recipes.experiment",
)


class RecipeRegistry:
    """Singleton registry for discovered recipes.

    Access recipes via `.path_to_recipe` attribute.
    """

    _instance: RecipeRegistry | None = None
    path_to_recipe: dict[str, Recipe]  # module_path -> Recipe
    _discovered: bool = False

    def __new__(cls) -> RecipeRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.path_to_recipe = {}
            cls._instance._discovered = False
        return cls._instance

    def _ensure_discovered(self) -> None:
        """Lazily discover all recipes on first access."""
        if not self._discovered:
            self.discover_all()

    def get(self, module_path: str) -> Recipe | None:
        """Get a recipe by module path (tries both short and full paths)."""
        self._ensure_discovered()

        # Try exact match first
        if module_path in self.path_to_recipe:
            return self.path_to_recipe[module_path]

        # Try with configured recipe prefixes if it's a short name.
        if not module_path.startswith("recipes."):
            for prefix in RECIPE_SEARCH_PREFIXES:
                if recipe := self.path_to_recipe.get(f"{prefix}.{module_path}"):
                    return recipe

        # Try to load directly as a fallback for recipes outside recipes package
        # This supports test fixtures and external recipe packages
        recipe = Recipe.load(module_path)
        if recipe is None:
            return None
        if not recipe.get_explicit_tool_makers():
            return None
        # Cache it for future lookups
        self.path_to_recipe[module_path] = recipe
        return recipe

    def get_all(self) -> list[Recipe]:
        """Get all discovered recipes."""
        self._ensure_discovered()
        return list(self.path_to_recipe.values())

    def discover_all(self, base_package: str | None = None) -> None:
        """Discover recipe modules and add them to registry.

        If ``base_package`` is provided, only that package is scanned.
        If omitted, all configured recipe namespaces are scanned.

        Args:
            base_package: Optional base package to search for recipes.
        """
        packages = RECIPE_SEARCH_PREFIXES if base_package is None else (base_package,)
        for package in packages:
            if importlib.util.find_spec(package) is None:
                continue
            base_module = importlib.import_module(package)

            # Get the package path
            if not hasattr(base_module, "__path__"):
                continue

            # Walk packages recursively
            for _importer, modname, ispkg in pkgutil.walk_packages(path=base_module.__path__, prefix=f"{package}."):
                # Skip private modules
                if any(part.startswith("_") for part in modname.split(".")):
                    continue
                if ispkg:
                    continue
                recipe = Recipe.load(modname)
                if recipe is None or not recipe.get_explicit_tool_makers():
                    continue
                self.path_to_recipe[modname] = recipe

        if base_package is None:
            self._discovered = True

    def clear(self) -> None:
        """Clear the registry (mainly for testing)."""
        self.path_to_recipe.clear()
        self._discovered = False


# Global singleton - access directly
recipe_registry = RecipeRegistry()
