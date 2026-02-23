"""Generic game play recipe — plays any registered game by name."""

from __future__ import annotations

import importlib
from typing import Optional

import metta.tools as tools
from metta.sim.simulation_config import SimulationConfig

_GAME_MODULES = {
    "hunger": "metta.games.hunger.missions",
}


def play(
    game: str = "hunger",
    policy_uri: Optional[str] = None,
    num_agents: int = 40,
    max_steps: int = 5000,
) -> tools.PlayTool:
    if game not in _GAME_MODULES:
        raise ValueError(f"Unknown game {game!r}. Available: {list(_GAME_MODULES.keys())}")
    mod = importlib.import_module(_GAME_MODULES[game])
    env = mod.make_game(num_agents=num_agents, max_steps=max_steps)
    sim = SimulationConfig(suite=game, name="basic", env=env)
    return tools.PlayTool(sim=sim, policy_uri=policy_uri)
