"""Registry system for scaffold types."""

from __future__ import annotations

from typing import Callable, Dict, Type

from cortex.config import ScaffoldConfig
from cortex.cores.base import MemoryCore
from cortex.scaffolds.base import BaseScaffold

ScaffoldBuilder = Callable[[ScaffoldConfig, int, MemoryCore], BaseScaffold]

_SCAFFOLD_REGISTRY: Dict[Type[ScaffoldConfig], Type[BaseScaffold]] = {}
_SCAFFOLD_CONFIG_BY_TAG: Dict[str, type[ScaffoldConfig]] = {}


def _get_scaffold_tag(config_class: type[ScaffoldConfig]) -> str:
    field = config_class.model_fields["scaffold_type"]  # type: ignore[attr-defined]
    tag = field.default  # type: ignore[assignment]
    if isinstance(tag, str) and tag:
        return tag
    raise ValueError(f"Scaffold config {config_class.__name__} must define a default 'scaffold_type' field")


def register_scaffold(config_class: Type[ScaffoldConfig]) -> Callable:
    """Register decorator linking scaffold class to its configuration type."""

    def decorator(scaffold_class: Type[BaseScaffold]) -> Type[BaseScaffold]:
        _SCAFFOLD_REGISTRY[config_class] = scaffold_class
        config_class._scaffold_class = scaffold_class  # type: ignore[attr-defined]

        tag = _get_scaffold_tag(config_class)
        if tag in _SCAFFOLD_CONFIG_BY_TAG and _SCAFFOLD_CONFIG_BY_TAG[tag] is not config_class:
            raise ValueError(
                f"Duplicate scaffold_type tag '{tag}' for {config_class.__name__};"
                f" already registered to {_SCAFFOLD_CONFIG_BY_TAG[tag].__name__}"
            )
        _SCAFFOLD_CONFIG_BY_TAG[tag] = config_class
        return scaffold_class

    return decorator


def get_scaffold_class(config: ScaffoldConfig) -> Type[BaseScaffold]:
    """Lookup scaffold class from a configuration instance."""
    config_type = type(config)
    if hasattr(config_type, "_scaffold_class"):
        return config_type._scaffold_class
    if config_type in _SCAFFOLD_REGISTRY:
        return _SCAFFOLD_REGISTRY[config_type]
    raise ValueError(f"No scaffold class registered for config type {config_type.__name__}")


def get_scaffold_config_class(tag: str) -> type[ScaffoldConfig]:
    if tag not in _SCAFFOLD_CONFIG_BY_TAG:
        raise KeyError(f"Unknown scaffold_type tag '{tag}' - is the scaffold registered?")
    return _SCAFFOLD_CONFIG_BY_TAG[tag]


def build_scaffold(config: ScaffoldConfig, d_hidden: int, core: MemoryCore) -> BaseScaffold:
    """Instantiate a scaffold from configuration using registry lookup."""
    return get_scaffold_class(config)(config=config, d_hidden=d_hidden, core=core)


__all__ = ["register_scaffold", "get_scaffold_class", "build_scaffold", "get_scaffold_config_class"]
