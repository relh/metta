"""Herbivore variant: requires plants, adds herbivore station (scout gear)."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from mettagrid.config.filter import actorHasAnyOf
from mettagrid.config.handler_config import Handler, updateActor
from mettagrid.config.mettagrid_config import GridObjectConfig, MettaGridConfig


def herbivore_station_config() -> GridObjectConfig:
    """Gear station that gives scout role. Once picked, cannot be changed."""
    return GridObjectConfig(
        name="herbivore_station",
        render_name="scout",
        on_use_handlers={
            "has_gear": Handler(
                filters=[actorHasAnyOf(["scrambler", "scout"])],
                mutations=[],
            ),
            "get_gear": Handler(
                filters=[],
                mutations=[updateActor({"scout": 1})],
            ),
        },
    )


class HerbivoreVariant(CoGameMissionVariant):
    """Requires plants. Adds herbivore station (scout gear)."""

    name: str = "herbivore"
    description: str = "Herbivores (scouts) can harvest plants for food."
    depends_on: list[str] = ["plants"]

    def modify_env(self, mission, env: MettaGridConfig) -> None:
        env.game.resource_names.append("scout")
        env.game.objects["herbivore_station"] = herbivore_station_config()

        for agent in env.game.agents:
            agent.inventory.limits["gear"].resources.append("scout")

        env.game.map_builder.instance.hub.stations.append("herbivore_station")
        env.game.map_builder.instance.hub.stations.append("herbivore_station")
