"""Herbivore variant: requires plant, adds herbivore station (herbivore gear)."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from mettagrid.config.filter import actorHasAnyOf
from mettagrid.config.handler_config import Handler, updateActor
from mettagrid.config.mettagrid_config import GridObjectConfig, MettaGridConfig
from mettagrid.config.render_config import RenderAsset


def herbivore_station_config() -> GridObjectConfig:
    """Gear station that gives herbivore role. Once picked, cannot be changed."""
    return GridObjectConfig(
        name="herbivore_station",
        on_use_handlers={
            "has_gear": Handler(
                filters=[actorHasAnyOf(["carnivore", "herbivore"])],
                mutations=[],
            ),
            "get_gear": Handler(
                filters=[],
                mutations=[updateActor({"herbivore": 1})],
            ),
        },
    )


class HerbivoreVariant(CoGameMissionVariant):
    """Requires plant. Adds herbivore station (herbivore gear)."""

    name: str = "herbivore"
    description: str = "Herbivores can harvest plant objects for food."
    depends_on: list[str] = ["plant"]

    def modify_env(self, mission, env: MettaGridConfig) -> None:
        env.game.resource_names.append("herbivore")
        env.game.objects["herbivore_station"] = herbivore_station_config()

        for agent in env.game.agents:
            agent.inventory.limits["gear"].resources.append("herbivore")

        env.game.map_builder.instance.hub.stations.append("herbivore_station")
        env.game.map_builder.instance.hub.stations.append("herbivore_station")

        env.game.render.assets["agent"].append(RenderAsset(asset="scout", resources=["herbivore"]))
        env.game.render.assets["herbivore_station"] = [RenderAsset(asset="scout")]
