"""Mission configuration for the Hunger game."""

from __future__ import annotations

from pydantic import Field

from cogames.core import CoGameMission
from metta.games.hunger.agent import agent_config
from metta.games.hunger.config import HungerConfig
from metta.games.hunger.seasons import season_events
from metta.games.hunger.stations import plant_config, predator_station_config, prey_station_config, wall_config
from mettagrid.config.action_config import ActionsConfig, MoveActionConfig, NoopActionConfig
from mettagrid.config.mettagrid_config import GameConfig, MettaGridConfig
from mettagrid.config.obs_config import ObsConfig
from mettagrid.map_builder.map_builder import AnyMapBuilderConfig


class HungerMission(CoGameMission):
    """Mission configuration for the Hunger game."""

    max_steps: int = Field(default=5000)
    num_agents: int = Field(default=40)

    @property
    def num_agents_prop(self) -> int:
        return self.num_cogs if self.num_cogs is not None else self.num_agents

    def map_builder(self) -> AnyMapBuilderConfig:
        return self.site.map_builder

    def make_env(self) -> MettaGridConfig:
        num = self.num_agents_prop
        game = GameConfig(
            map_builder=self.map_builder(),
            max_steps=self.max_steps,
            num_agents=num,
            resource_names=HungerConfig.RESOURCES,
            obs=ObsConfig(),
            actions=ActionsConfig(
                move=MoveActionConfig(),
                noop=NoopActionConfig(),
            ),
            agents=[agent_config(max_steps=self.max_steps) for _ in range(num)],
            objects={
                "wall": wall_config(),
                "plant": plant_config(),
                "predator_station": predator_station_config(),
                "prey_station": prey_station_config(),
            },
            events=season_events(
                self.max_steps,
                num_cogs=num,
                num_plants=HungerConfig.estimate_num_plants(num),
            ),
        )
        env = MettaGridConfig(game=game)
        env = env.model_copy(deep=True)
        env.label = self.full_name()

        for variant in self.variants:
            variant.modify_env(self, env)
            env.label += f".{variant.name}"

        return env
