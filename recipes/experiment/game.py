"""Generic game play recipe — plays any registered game by name."""

from __future__ import annotations

from typing import Optional, Sequence

import metta.tools as tools
from metta.games.games import GAMES, make_game
from metta.sim.simulation_config import SimulationConfig
from mettagrid.policy.loader import discover_and_register_policies


def play(
    game: str = "hunger",
    policy_uri: Optional[str] = None,
    num_agents: int = 40,
    cogs: Optional[int] = None,
    max_steps: Optional[int] = None,
    variants: Optional[Sequence[str]] = None,
) -> tools.PlayTool:
    if game not in GAMES:
        raise ValueError(f"Unknown game {game!r}. Available: {list(GAMES.keys())}")

    info = GAMES[game]
    if policy_uri is None:
        policy_uri = info.get("policy_uri")
    for pkg in info.get("policy_packages", []):
        discover_and_register_policies(pkg)

    if isinstance(variants, str):
        variant_list = [v.strip() for v in variants.split(",") if v.strip()]
    else:
        variant_list = list(variants) if variants else []
    env = make_game(
        game,
        num_agents=num_agents,
        cogs=cogs,
        max_steps=max_steps,
        variants=variant_list if variant_list else None,
    )
    sim = SimulationConfig(suite=game, name="basic", env=env)
    steps = max_steps if max_steps is not None else env.game.max_steps
    return tools.PlayTool(sim=sim, policy_uri=policy_uri, max_steps=steps)
