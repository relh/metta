from metta.app_backend.tournament.referees.envs import make_cogsguard_env
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase
from mettagrid.config.mettagrid_config import MettaGridConfig

NUM_AGENTS = 10


class CogsguardSelfPlayReferee(SelfPlayRefereeBase):
    num_agents: int = NUM_AGENTS
    game_tag: str = "cogsguard"
    description: str = "Self-play matches on CogsGuard arena"
    # TODO: Re-enable replays once mettascope supports the new cogsguard config format
    skip_replay: bool = True

    def make_env(self, seed: int) -> MettaGridConfig:
        return make_cogsguard_env(seed, self.num_agents)


class CogsguardPairingReferee(PairingRefereeBase):
    num_agents: int = NUM_AGENTS
    game_tag: str = "cogsguard"
    match_configurations: list[list[int]] = [
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 1],  # 1v9
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],  # 9v1
        [0, 0, 0, 0, 0, 1, 1, 1, 1, 1],  # 5v5
    ]
    description: str = (
        "Pairwise matchups on CogsGuard arena with varied agent splits (1+9, 9+1, 5+5); "
        "scored by participation-weighted average"
    )
    # TODO: Re-enable replays once mettascope supports the new cogsguard config format
    skip_replay: bool = True

    def make_env(self, seed: int) -> MettaGridConfig:
        return make_cogsguard_env(seed, self.num_agents)
