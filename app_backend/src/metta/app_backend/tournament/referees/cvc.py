from metta.app_backend.tournament.referees.envs import make_shared_rewards_env
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase
from mettagrid.config.mettagrid_config import MettaGridConfig

NUM_AGENTS = 5


class CvcSelfPlayReferee(SelfPlayRefereeBase):
    num_agents: int = NUM_AGENTS
    game_tag: str = "cvc"
    description: str = "Self-play matches on Machina 1 Open World"

    def make_env(self, seed: int) -> MettaGridConfig:
        return make_shared_rewards_env(seed, self.num_agents)


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
        "Pairwise matchups on Machina 1 Open World with varied agent splits (1+4, 4+1, 2+3); "
        "scored by participation-weighted average"
    )

    def make_env(self, seed: int) -> MettaGridConfig:
        return make_shared_rewards_env(seed, self.num_agents)
