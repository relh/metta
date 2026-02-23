"""Map/site definitions for the Hunger game."""

from __future__ import annotations

from cogames.cogs_vs_clips.terrain import MachinaArena
from cogames.core import CoGameSite
from metta.games.hunger.config import HungerConfig
from mettagrid.mapgen.mapgen import MapGen
from mettagrid.mapgen.scenes.base_hub import BaseHub


def hunger_site(num_agents: int = 40) -> CoGameSite:
    """Create a Hunger game site with forest biome, scattered plants, and gear stations."""
    return CoGameSite(
        name="hunger_arena",
        description="Hunger arena with plants, predator and prey stations.",
        map_builder=MapGen.Config(
            width=88,
            height=88,
            instance=MachinaArena.Config(
                spawn_count=80,
                base_biome="forest",
                base_biome_config={"seed_prob": 0.015},
                building_coverage=HungerConfig.PLANT_DENSITY,
                building_names=["plant"],
                building_weights={"plant": 1.0},
                biome_weights={"forest": 1.0},
                dungeon_weights={"none": 1.0},
                hub=BaseHub.Config(
                    spawn_count=num_agents,
                    hub_object="plant",
                    corner_bundle="custom",
                    corner_objects=["plant", "plant", "plant", "plant"],
                    cross_bundle="custom",
                    cross_objects=["predator_station", "predator_station", "prey_station", "prey_station"],
                    cross_distance=7,
                    junction_object="plant",
                    randomize_spawn_positions=True,
                ),
            ),
        ),
        min_cogs=1,
        max_cogs=num_agents,
    )


HUNGER_ARENA = hunger_site(num_agents=40)
