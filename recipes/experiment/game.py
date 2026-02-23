"""Generic game play recipe — plays any registered game by name."""

from __future__ import annotations

import importlib
from typing import Optional

import metta.tools as tools
from metta.sim.simulation_config import SimulationConfig
from mettagrid.policy.loader import discover_and_register_policies

_GAME_MODULES = {
    "hunger": "metta.games.hunger.missions",
}

_GAME_DEFAULTS = {
    "hunger": {
        "policy_uri": "metta://policy/hunger_agent",
        "policy_packages": ["metta.games.hunger.agent.hunger_agent"],
    },
}


def play(
    game: str = "hunger",
    policy_uri: Optional[str] = None,
    num_agents: int = 40,
    max_steps: int = 5000,
) -> tools.PlayTool:
    if game not in _GAME_MODULES:
        raise ValueError(f"Unknown game {game!r}. Available: {list(_GAME_MODULES.keys())}")

    defaults = _GAME_DEFAULTS.get(game, {})
    if policy_uri is None:
        policy_uri = defaults.get("policy_uri")
    for pkg in defaults.get("policy_packages", []):
        discover_and_register_policies(pkg)

    mod = importlib.import_module(_GAME_MODULES[game])
    env = mod.make_game(num_agents=num_agents, max_steps=max_steps)
    sim = SimulationConfig(suite=game, name="basic", env=env)
    return tools.PlayTool(sim=sim, policy_uri=policy_uri)
