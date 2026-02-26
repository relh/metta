"""Game configuration for the Hunger game."""

from __future__ import annotations

from typing import cast

from pydantic import Field

from cogames.cogs_vs_clips.terrain import MachinaArena
from cogames.core import CoGameMission, CoGameSite
from metta.games.games import register  # noqa: E402
from metta.games.hunger.variants import parse_variants
from mettagrid.config.action_config import ActionsConfig, MoveActionConfig, NoopActionConfig
from mettagrid.config.mettagrid_config import (
    AgentConfig,
    GameConfig,
    InventoryConfig,
    MettaGridConfig,
    ResourceLimitsConfig,
    WallConfig,
)
from mettagrid.config.obs_config import GlobalObsConfig, ObsConfig
from mettagrid.config.render_config import RenderConfig
from mettagrid.mapgen.mapgen import MapGen
from mettagrid.mapgen.scenes.base_hub import BaseHub


class HungerGame(CoGameMission):
    max_steps: int = Field(default=250)  # 1 year; use multi_year_5 or multi_year_10 for longer

    @classmethod
    def create(cls, num_agents: int, max_steps: int) -> HungerGame:
        return cls(
            name="basic",
            description="Hunger game",
            site=cls._map(num_agents),
            num_cogs=num_agents,
            max_steps=max_steps,
        )

    def make_env(self) -> MettaGridConfig:
        num_cogs = cast(int, self.num_cogs)  # always set by create()
        game = GameConfig(
            map_builder=self.site.map_builder,
            max_steps=self.max_steps,
            num_agents=num_cogs,
            resource_names=[],
            obs=ObsConfig(
                global_obs=GlobalObsConfig(
                    local_position=True,
                    last_action_move=True,
                ),
            ),
            actions=ActionsConfig(
                move=MoveActionConfig(),
                noop=NoopActionConfig(),
            ),
            agents=[
                AgentConfig(
                    inventory=InventoryConfig(
                        limits={
                            "gear": ResourceLimitsConfig(min=1, max=1, resources=[]),
                        },
                    ),
                    rewards={},
                )
                for _ in range(num_cogs)
            ],
            objects={
                "wall": WallConfig(name="wall"),
            },
            render=RenderConfig(
                assets={
                    "agent": [],
                },
                object_status={"agent": {}},
            ),
        )
        return MettaGridConfig(game=game)

    @staticmethod
    def _map(num_agents: int) -> CoGameSite:
        return CoGameSite(
            name="hunger_arena",
            description="Hunger arena. Add variants=plant, herbivore, or carnivore.",
            map_builder=MapGen.Config(
                width=88,
                height=88,
                instance=MachinaArena.Config(
                    spawn_count=80,
                    base_biome="forest",
                    base_biome_config={"seed_prob": 0.015},
                    building_coverage=0,
                    building_names=[],
                    building_weights={},
                    biome_weights={"forest": 1.0},
                    dungeon_weights={"none": 1.0},
                    hub=BaseHub.Config(
                        spawn_count=num_agents,
                        hub_object="empty",
                        corner_bundle="none",
                        cross_bundle="none",
                        cross_distance=7,
                        randomize_spawn_positions=True,
                    ),
                ),
            ),
            min_cogs=1,
            max_cogs=num_agents,
        )


register(
    "hunger",
    HungerGame,
    parse_variants=parse_variants,
    policy_uri="metta://policy/hunger_agent",
    policy_packages=["metta.games.hunger.agent.hunger_agent"],
)
