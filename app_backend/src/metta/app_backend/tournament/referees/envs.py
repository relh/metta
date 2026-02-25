from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cogames.cogs_vs_clips.mission import CvCMission
from cogames.cogs_vs_clips.missions import CogsGuardMachina1Mission, MettaGridConfig, make_cogsguard_mission
from cogames.cogs_vs_clips.sites import COGSGUARD_MACHINA_1
from cogames.cogs_vs_clips.variants import NoClipsVariant

GameFactory = Callable[[int, int], MettaGridConfig]


def make_cogsguard_env(seed: int, num_agents: int, max_steps: int = 10000) -> MettaGridConfig:
    mission = make_cogsguard_mission(num_agents=num_agents, max_steps=max_steps)
    env = mission.make_env()
    env.game.map_builder.seed = seed  # type: ignore
    return env


def make_cvc_env(seed: int, num_agents: int) -> MettaGridConfig:
    mission = CogsGuardMachina1Mission.model_copy(deep=True)
    mission.num_cogs = num_agents
    env = mission.make_env()
    env.game.map_builder.seed = seed  # type: ignore
    return env


def make_no_clips_env(seed: int, num_agents: int) -> MettaGridConfig:
    mission = CvCMission(
        name="no_clips",
        description="CogsGuard Machina1 with clips disabled",
        site=COGSGUARD_MACHINA_1,
        num_cogs=num_agents,
        max_steps=10000,
    )
    mission = mission.with_variants([NoClipsVariant()])
    env = mission.make_env()
    env.game.map_builder.seed = seed  # type: ignore
    return env


def make_no_clips_no_vibes_env(seed: int, num_agents: int) -> MettaGridConfig:
    mission = CvCMission(
        name="no_clips_no_vibes",
        description="CogsGuard Machina1 with clips and vibe changing disabled",
        site=COGSGUARD_MACHINA_1,
        num_cogs=num_agents,
        max_steps=10000,
    )
    mission = mission.with_variants([NoClipsVariant()])
    env = mission.make_env()
    env.game.actions.change_vibe.enabled = False
    env.game.map_builder.seed = seed  # type: ignore
    return env


_GAME_SPECS: dict[str, tuple[int, GameFactory]] = {
    "cogsguard_4agents": (4, make_cogsguard_env),
    "cogsguard_8agents": (8, make_cogsguard_env),
    "cogsguard_10agents": (10, make_cogsguard_env),
    "cogsguard_machina_1_5agents": (5, make_cvc_env),
    "cogsguard_machina_1_8agents": (8, make_cvc_env),
    "cogsguard_machina_1_no_clips_8agents": (8, make_no_clips_env),
    "cogsguard_machina_1_no_clips_no_vibes_8agents": (8, make_no_clips_no_vibes_env),
}


def _get_game_spec(env_name: str) -> tuple[int, GameFactory]:
    spec = _GAME_SPECS.get(env_name)
    if spec is None:
        supported = ", ".join(sorted(_GAME_SPECS))
        raise ValueError(f"Unknown tournament game '{env_name}'. Supported games: {supported}")
    return spec


class GameEnvGenerator(BaseModel):
    model_config = ConfigDict(frozen=True)
    env_name: str = "cogsguard_8agents"
    num_agents: int = Field(default=8, description="Number of agents in the game environment")

    @model_validator(mode="after")
    def _validate_registered_game(self) -> "GameEnvGenerator":
        expected_num_agents, _ = _get_game_spec(self.env_name)
        if self.num_agents != expected_num_agents:
            raise ValueError(
                f"Game '{self.env_name}' has fixed num_agents={expected_num_agents}, got {self.num_agents}"
            )
        return self

    def generate(self, seed: int) -> MettaGridConfig:
        _, generate = _get_game_spec(self.env_name)
        return generate(seed, self.num_agents)


GAME_REGISTRY: dict[str, GameEnvGenerator] = {
    env_name: GameEnvGenerator(env_name=env_name, num_agents=num_agents)
    for env_name, (num_agents, _) in _GAME_SPECS.items()
}


def get_game(env_name: str) -> GameEnvGenerator:
    game = GAME_REGISTRY.get(env_name)
    if game is None:
        supported = ", ".join(sorted(GAME_REGISTRY))
        raise ValueError(f"Unknown tournament game '{env_name}'. Supported games: {supported}")
    return game
