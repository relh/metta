"""Plants variant: adds plants (harvest requires scout/herbivore). Use seasons variant for food drops."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from mettagrid.config.filter.filter import isNot
from mettagrid.config.handler_config import Handler, actorHas, targetHas, withdraw
from mettagrid.config.mettagrid_config import GridObjectConfig, InventoryConfig, MettaGridConfig

INITIAL_PLANT_FOOD = 1
MAX_PLANT_FOOD = 100
PLANT_DENSITY = 0.016
MAP_WIDTH = 88
MAP_HEIGHT = 88


class PlantsVariant(CoGameMissionVariant):
    """Add plants: scatter on map, hub placement. Harvest requires scout (herbivore)."""

    name: str = "plants"
    description: str = "Plants scatter the map. Herbivores (scouts) harvest for food."
    depends_on: list[str] = ["food"]

    def modify_env(self, mission, env: MettaGridConfig) -> None:
        env.game.objects["plants"] = plants_config()

        instance = getattr(env.game.map_builder, "instance", None)
        if instance is not None:
            instance.building_coverage = PLANT_DENSITY
            instance.building_names = ["plants"]
            instance.building_weights = {"plants": 1.0}
            if instance.hub is not None:
                instance.hub.hub_object = "plants"
                instance.hub.corner_bundle = "custom"
                instance.hub.corner_objects = ["plants", "plants", "plants", "plants"]
                instance.hub.cross_bundle = "custom"
                instance.hub.cross_objects = ["plants", "plants", "plants", "plants"]


def plants_config() -> GridObjectConfig:
    """Plant with harvest handlers. Requires scout (herbivore) gear."""
    return GridObjectConfig(
        name="plants",
        render_name="junction",
        inventory=InventoryConfig(initial={"food": INITIAL_PLANT_FOOD}, default_limit=MAX_PLANT_FOOD),
        on_use_handlers={
            "harvest_last": Handler(
                filters=[actorHas({"scout": 1}), isNot(targetHas({"food": 2}))],
                mutations=[withdraw({"food": 100})],
            ),
            "harvest": Handler(
                filters=[actorHas({"scout": 1})],
                mutations=[withdraw({"food": 100})],
            ),
        },
    )
