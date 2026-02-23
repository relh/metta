"""Mission registry for the Hunger game."""

from __future__ import annotations

from metta.games.hunger.mission import HungerMission
from metta.games.hunger.sites import HUNGER_ARENA, hunger_site
from mettagrid.config.mettagrid_config import MettaGridConfig

HungerBasicMission = HungerMission(
    name="basic",
    description="Hunger arena - predator/prey survival with seasonal egg cycles.",
    site=HUNGER_ARENA,
    num_cogs=40,
    max_steps=5000,
)

MISSIONS: list[HungerMission] = [
    HungerBasicMission,
]


def make_game(num_agents: int = 40, max_steps: int = 5000) -> MettaGridConfig:
    """Create a Hunger game environment config."""
    mission = HungerMission(
        name="basic",
        description="Hunger game",
        site=hunger_site(num_agents),
        num_cogs=num_agents,
        max_steps=max_steps,
    )
    return mission.make_env()
