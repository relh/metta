from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cogames.cogs_vs_clips.mission import CvCMission
from cogames.cogs_vs_clips.missions import CogsGuardMachina1Mission, MettaGridConfig, make_cogsguard_mission
from cogames.cogs_vs_clips.sites import COGSGUARD_MACHINA_1
from cogames.cogs_vs_clips.variants import NoClipsVariant

GameFactory = Callable[[int, int], MettaGridConfig]

COGSGUARD_GAME_DESCRIPTION = """\
Cogs v Clips is a team-based territory control game. Cog agents capture and hold \
junctions while Clips — automated opponents — continuously expand by seizing adjacent territory.

**Roles** — Miners gather resources, Aligners capture neutral junctions, Scramblers \
neutralize enemy junctions, and Scouts explore. No role succeeds alone.

**Territory** — Friendly territory restores energy and HP; enemy territory drains both. \
Hearts (crafted from mined resources) are spent to capture or disrupt junctions.

**Scoring** — Every tick, your team earns reward proportional to the territory it holds.\
"""


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


@dataclass(frozen=True)
class _GameSpec:
    num_agents: int
    factory: GameFactory
    base_description: str = ""
    variant_note: str = ""

    @property
    def game_description(self) -> str:
        if not self.base_description:
            return ""
        if not self.variant_note:
            return self.base_description
        return f"{self.base_description}\n\n**Variant** — {self.variant_note}"


_GAME_SPECS: dict[str, _GameSpec] = {
    "cogsguard_4agents": _GameSpec(4, make_cogsguard_env, COGSGUARD_GAME_DESCRIPTION),
    "cogsguard_8agents": _GameSpec(8, make_cogsguard_env, COGSGUARD_GAME_DESCRIPTION),
    "cogsguard_10agents": _GameSpec(10, make_cogsguard_env, COGSGUARD_GAME_DESCRIPTION),
    "cogsguard_machina_1_5agents": _GameSpec(5, make_cvc_env, COGSGUARD_GAME_DESCRIPTION),
    "cogsguard_machina_1_8agents": _GameSpec(8, make_cvc_env, COGSGUARD_GAME_DESCRIPTION),
    "cogsguard_machina_1_no_clips_8agents": _GameSpec(
        8, make_no_clips_env, COGSGUARD_GAME_DESCRIPTION, "Clips are disabled. No automated territorial pressure."
    ),
    "cogsguard_machina_1_no_clips_no_vibes_8agents": _GameSpec(
        8,
        make_no_clips_no_vibes_env,
        COGSGUARD_GAME_DESCRIPTION,
        "Clips are disabled and agents cannot change vibes.",
    ),
}


def _get_game_spec(env_name: str) -> _GameSpec:
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
        spec = _get_game_spec(self.env_name)
        if self.num_agents != spec.num_agents:
            raise ValueError(f"Game '{self.env_name}' has fixed num_agents={spec.num_agents}, got {self.num_agents}")
        return self

    @property
    def game_description(self) -> str:
        return _get_game_spec(self.env_name).game_description

    def generate(self, seed: int) -> MettaGridConfig:
        return _get_game_spec(self.env_name).factory(seed, self.num_agents)


GAME_REGISTRY: dict[str, GameEnvGenerator] = {
    env_name: GameEnvGenerator(env_name=env_name, num_agents=spec.num_agents) for env_name, spec in _GAME_SPECS.items()
}


def get_game(env_name: str) -> GameEnvGenerator:
    game = GAME_REGISTRY.get(env_name)
    if game is None:
        supported = ", ".join(sorted(GAME_REGISTRY))
        raise ValueError(f"Unknown tournament game '{env_name}'. Supported games: {supported}")
    return game
