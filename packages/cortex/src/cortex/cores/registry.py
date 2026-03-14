"""Registry for memory cores."""

from typing import Callable, Type

from cortex.config import CoreConfig
from cortex.cores.base import MemoryCore

_CORE_REGISTRY: dict[Type[CoreConfig], Type[MemoryCore]] = {}
_CORE_CONFIG_BY_TAG: dict[str, Type[CoreConfig]] = {}


def _get_core_tag(config_class: type[CoreConfig]) -> str:
    field = config_class.model_fields["core_type"]  # type: ignore[attr-defined]
    tag = field.default  # type: ignore[assignment]
    if isinstance(tag, str) and tag:
        return tag
    raise ValueError(f"Core config {config_class.__name__} must define a default 'core_type' field")


def register_core(config_class: Type[CoreConfig]) -> Callable:
    """Register decorator linking core class to its configuration type."""

    def decorator(core_class: Type[MemoryCore]) -> Type[MemoryCore]:
        _CORE_REGISTRY[config_class] = core_class
        config_class._core_class = core_class  # type: ignore[attr-defined]

        tag = _get_core_tag(config_class)
        if tag in _CORE_CONFIG_BY_TAG and _CORE_CONFIG_BY_TAG[tag] is not config_class:
            raise ValueError(
                f"Duplicate core_type tag '{tag}' for {config_class.__name__};"
                f" already registered to {_CORE_CONFIG_BY_TAG[tag].__name__}"
            )
        _CORE_CONFIG_BY_TAG[tag] = config_class
        return core_class

    return decorator


def get_core_class(config: CoreConfig) -> Type[MemoryCore]:
    """Lookup core class from a configuration instance."""
    config_type = type(config)
    if config_type not in _CORE_REGISTRY:
        raise ValueError(f"No core registered for config type {config_type.__name__}")
    return _CORE_REGISTRY[config_type]


def get_core_config_class(tag: str) -> type[CoreConfig]:
    """Return the CoreConfig subclass registered for a given tag."""
    if tag not in _CORE_CONFIG_BY_TAG:
        raise KeyError(f"Unknown core_type tag '{tag}' - is the core registered?")
    return _CORE_CONFIG_BY_TAG[tag]


def build_core(config: CoreConfig) -> MemoryCore:
    """Instantiate a core from configuration using registry lookup."""
    return get_core_class(config)(config)


__all__ = ["register_core", "build_core", "get_core_class", "get_core_config_class"]
