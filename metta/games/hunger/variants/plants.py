"""Plant variant: adds plant objects (harvest requires herbivore). Use seasons variant for food drops."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from mettagrid.config.filter.filter import isNot
from mettagrid.config.handler_config import Handler, actorHas, targetHas, withdraw
from mettagrid.config.mettagrid_config import GridObjectConfig, InventoryConfig, MettaGridConfig
from mettagrid.config.render_config import RenderAsset

INITIAL_PLANT_FOOD = 1
MAX_PLANT_FOOD = 100
PLANT_DENSITY = 0.016
MAP_WIDTH = 88
MAP_HEIGHT = 88


class PlantVariant(CoGameMissionVariant):
    """Add plant objects: scatter on map, hub placement. Harvest requires herbivore."""

    name: str = "plant"
    description: str = "Plant objects scatter the map. Herbivores harvest for food."
    depends_on: list[str] = ["food"]

    def modify_env(self, mission, env: MettaGridConfig) -> None:
        env.game.objects["plant"] = plant_config()
        env.game.render.assets["plant"] = [
            RenderAsset(asset="junction.working", resources=["food"]),
            RenderAsset(asset="junction"),
        ]

        instance = getattr(env.game.map_builder, "instance", None)
        if instance is not None:
            instance.building_coverage = PLANT_DENSITY
            instance.building_names = ["plant"]
            instance.building_weights = {"plant": 1.0}
            if instance.hub is not None:
                instance.hub.hub_object = "plant"
                instance.hub.corner_bundle = "custom"
                instance.hub.corner_objects = ["plant", "plant", "plant", "plant"]
                instance.hub.cross_bundle = "custom"
                instance.hub.cross_objects = ["plant", "plant", "plant", "plant"]


def plant_config() -> GridObjectConfig:
    """Plant with harvest handlers. Requires herbivore gear."""
    return GridObjectConfig(
        name="plant",
        inventory=InventoryConfig(initial={"food": INITIAL_PLANT_FOOD}, default_limit=MAX_PLANT_FOOD),
        on_use_handlers={
            "harvest_last": Handler(
                filters=[actorHas({"herbivore": 1}), isNot(targetHas({"food": 2}))],
                mutations=[withdraw({"food": 100})],
            ),
            "harvest": Handler(
                filters=[actorHas({"herbivore": 1})],
                mutations=[withdraw({"food": 100})],
            ),
        },
    )
