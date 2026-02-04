from cogames.cogs_vs_clips.mission import CvCMission
from cogames.cogs_vs_clips.sites import COGSGUARD_MACHINA_1
from cogames.cogs_vs_clips.variants import NoClipsVariant
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase
from mettagrid.config.mettagrid_config import MettaGridConfig

NUM_AGENTS = 8


def _make_no_clips_env(seed: int, num_agents: int) -> MettaGridConfig:
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


class NoClipsSelfPlayReferee(SelfPlayRefereeBase):
    num_agents: int = NUM_AGENTS
    game_tag: str = "cogsguard_machina_1_no_clips"
    description: str = "Self-play matches on CogsGuard Machina1 (8 agents, clips disabled)"

    def make_env(self, seed: int) -> MettaGridConfig:
        return _make_no_clips_env(seed, self.num_agents)


class NoClipsPairingReferee(PairingRefereeBase):
    num_agents: int = NUM_AGENTS
    game_tag: str = "cogsguard_machina_1_no_clips"
    match_configurations: list[list[int]] = [
        [0, 0, 1, 1, 1, 1, 1, 1],  # 2v6
        [0, 0, 0, 0, 0, 0, 1, 1],  # 6v2
        [0, 0, 0, 0, 1, 1, 1, 1],  # 4v4
    ]
    description: str = (
        "Pairwise matchups on CogsGuard Machina1 with 8 agents (2+6, 6+2, 4+4), clips disabled; "
        "scored by participation-weighted average"
    )

    def make_env(self, seed: int) -> MettaGridConfig:
        return _make_no_clips_env(seed, self.num_agents)
