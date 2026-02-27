"""Recipe abstraction for tool discovery.

A Recipe represents a module that defines tool makers - functions that return tool instances.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from types import ModuleType
from typing import Callable, Optional, cast

from typing_extensions import get_type_hints

from metta.common.tool import Tool

ToolMaker = Callable[..., Tool]


logger = logging.getLogger(__name__)


class Recipe:
    """Represents a recipe module that can provide tool makers."""

    def __init__(self, module: ModuleType):
        self.module = module
        self.module_name = module.__name__
        # Build tool maker map on initialization: maker_name -> tool_maker
        self._maker_name_to_tool_maker: dict[str, ToolMaker] = {}
        # Also build reverse map: tool_type -> list of (maker_name, tool_maker)
        self._tool_type_to_makers: dict[str, list[tuple[str, ToolMaker]]] = {}
        self._build_tool_maps()

    @property
    def short_name(self) -> str:
        """Get short name by removing recipes.prod. or recipes.experiment. prefix."""
        name = self.module_name
        for prefix in ["recipes.prod.", "recipes.experiment."]:
            if name.startswith(prefix):
                return name[len(prefix) :]
        return name

    def _build_tool_maps(self) -> None:
        """Build maker_name->tool_maker and tool_class_name->makers maps."""
        for name in dir(self.module):
            if name.startswith("_"):
                continue

            attr = getattr(self.module, name)
            if not callable(attr) or isinstance(attr, type):
                continue

            try:
                return_type = get_type_hints(attr).get("return")
            except (AttributeError, ImportError, NameError, TypeError, ValueError):
                continue

            if return_type is None or not isinstance(return_type, type) or not issubclass(return_type, Tool):
                continue

            maker = cast(ToolMaker, attr)
            self._maker_name_to_tool_maker[name] = maker

            tool_type = return_type.tool_type_name()
            self._tool_type_to_makers.setdefault(tool_type, []).append((name, maker))

    @classmethod
    def load(cls, module_path: str) -> Optional["Recipe"]:
        """Try to load a recipe from a module path. e.g. 'recipes.experiment.arena'"""
        if importlib.util.find_spec(module_path) is None:
            return None

        try:
            module = importlib.import_module(module_path)
        except Exception as exc:  # pragma: no cover - best-effort import guard
            logger.debug("Skipping recipe %s due to import failure: %s", module_path, exc)
            return None

        return cls(module)

    def get_explicit_tool_makers(self) -> dict[str, ToolMaker]:
        """Returns only tool makers explicitly defined in this recipe."""
        return dict(self._maker_name_to_tool_maker)

    def get_all_tool_maker_names(self) -> set[str]:
        """Get all tool maker names available from this recipe."""
        return set(self._maker_name_to_tool_maker)

    def get_tool_maker(self, name: str) -> ToolMaker | None:
        """Get a tool maker by maker name or tool type.

        Args:
            name: Either a maker name (e.g., 'replay_null', 'train_shaped')
                  or a tool type (e.g., 'evaluate', 'train')

        Returns:
            Tool maker, or None if not found
        """
        # Try direct maker name lookup first
        if name in self._maker_name_to_tool_maker:
            return self._maker_name_to_tool_maker[name]

        # Try tool type lookup (returns first matching maker)
        makers = self._tool_type_to_makers.get(name, [])
        if makers:
            return makers[0][1]

        return None

    def get_makers_for_tool(self, tool_type: str) -> list[tuple[str, ToolMaker]]:
        """Get all tool makers that return the given tool type.

        Useful for listing all implementations of a tool type (e.g., 'train', 'train_shaped').

        Args:
            tool_type: Tool type identifier (e.g., 'train', 'evaluate')

        Returns:
            List of (maker_name, tool_maker) tuples
        """
        return self._tool_type_to_makers.get(tool_type, [])
