from cogames.cogs_vs_clips.missions import CogsGuardMachina1Mission
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase
from mettagrid.config.mettagrid_config import MettaGridConfig

NUM_AGENTS = 5


def _make_env(seed: int, num_agents: int) -> MettaGridConfig:
    mission = CogsGuardMachina1Mission.model_copy(deep=True)
    mission.num_cogs = num_agents
    env = mission.make_env()
    env.game.map_builder.seed = seed  # type: ignore
    return env


class CvcSelfPlayReferee(SelfPlayRefereeBase):
    num_agents: int = NUM_AGENTS
    game_tag: str = "cvc"
    description: str = "Self-play matches on CogsGuard Machina1"

    def make_env(self, seed: int) -> MettaGridConfig:
        return _make_env(seed, self.num_agents)


class CvcPairingReferee(PairingRefereeBase):
    num_agents: int = NUM_AGENTS
    game_tag: str = "cvc"
    match_configurations: list[list[int]] = [
        [0, 1, 1, 1, 1],  # 1v4
        [0, 0, 0, 0, 1],  # 4v1
        [0, 0, 1, 1, 1],  # 2v3
        [0, 0, 0, 1, 1],  # 3v2
    ]
    description: str = (
        "Pairwise matchups on CogsGuard Machina1 with varied agent splits (1+4, 4+1, 2+3); "
        "scored by participation-weighted average"
    )

    def make_env(self, seed: int) -> MettaGridConfig:
        return _make_env(seed, self.num_agents)
