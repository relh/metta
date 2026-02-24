"""Carnivore variant: adds carnivore station, scrambler gear, and carnivore-herbivore handlers."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from mettagrid.config.filter import actorHasAnyOf
from mettagrid.config.handler_config import Handler, actorHas, targetHas, updateActor, updateTarget, withdraw
from mettagrid.config.mettagrid_config import GridObjectConfig, MettaGridConfig


class CarnivoreVariant(CoGameMissionVariant):
    """Add carnivores: scrambler gear, carnivore station, and carnivore-herbivore interactions."""

    name: str = "carnivore"
    description: str = "Carnivores (scramblers) can tag herbivores and steal food."
    depends_on: list[str] = ["food"]

    @staticmethod
    def carnivore_station_config() -> GridObjectConfig:
        """Gear station that gives scrambler role. Once picked, cannot be changed."""
        return GridObjectConfig(
            name="carnivore_station",
            render_name="scrambler",
            on_use_handlers={
                "has_gear": Handler(
                    filters=[actorHasAnyOf(["scrambler", "scout"])],
                    mutations=[],
                ),
                "get_gear": Handler(
                    filters=[],
                    mutations=[updateActor({"scrambler": 1})],
                ),
            },
        )

    def modify_env(self, mission, env: MettaGridConfig) -> None:
        env.game.resource_names.append("scrambler")
        env.game.objects["carnivore_station"] = self.carnivore_station_config()

        for agent in env.game.agents:
            agent.inventory.limits["gear"].resources.append("scrambler")
            agent.on_use_handlers["eat_prey"] = Handler(
                filters=[actorHas({"scrambler": 1}), targetHas({"scout": 1})],
                mutations=[withdraw({"food": 9999})],
            )
            agent.on_use_handlers["fight_predator"] = Handler(
                filters=[actorHas({"scrambler": 1}), targetHas({"scrambler": 1})],
                mutations=[updateActor({"egg": -1}), updateTarget({"egg": -1})],
            )

        instance = getattr(env.game.map_builder, "instance", None)
        if instance is not None and hasattr(instance, "hub") and instance.hub is not None:
            instance.hub.stations.append("carnivore_station")
            instance.hub.stations.append("carnivore_station")
