"""Game registry. Each game registers itself on import."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from mettagrid.config.mettagrid_config import MettaGridConfig

GAMES: dict[str, dict[str, Any]] = {}


def register(
    name: str,
    mission_class: type,
    *,
    parse_variants: Callable[[list[str]], list] | None = None,
    policy_uri: str | None = None,
    policy_packages: Sequence[str] | None = None,
) -> None:
    """Register a game. Mission class must have create(num_agents, max_steps) -> mission."""
    GAMES[name] = {
        "mission_class": mission_class,
        "parse_variants": parse_variants,
        "policy_uri": policy_uri,
        "policy_packages": list(policy_packages or []),
    }


def make_game(
    game: str,
    num_agents: int = 40,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
    **kwargs: Any,
) -> MettaGridConfig:
    """Create a game environment by name. Use cogs=N to set num_agents."""
    if game not in GAMES:
        raise ValueError(f"Unknown game {game!r}. Available: {list(GAMES.keys())}")
    n = cogs if cogs is not None else num_agents
    info = GAMES[game]
    mission_cls = info["mission_class"]
    if max_steps is None:
        field = mission_cls.model_fields.get("max_steps")
        max_steps = field.default if field is not None else 10000
        if callable(max_steps):
            max_steps = max_steps()
    mission = mission_cls.create(n, max_steps)
    if variants and info.get("parse_variants"):
        mission = mission.with_variants(info["parse_variants"](list(variants)))
    env = mission.make_env()
    env = env.model_copy(deep=True)
    env.label = mission.full_name()
    for variant in mission.variants:
        variant.modify_env(mission, env)
        env.label += f".{variant.name}"
    return env


# Import games to trigger self-registration
from metta.games.hunger import game as _  # noqa: E402, F401
