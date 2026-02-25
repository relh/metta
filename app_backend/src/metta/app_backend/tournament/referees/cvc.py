from metta.app_backend.tournament.referees.envs import get_game
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase

CVC_GAME = get_game("cogsguard_machina_1_5agents")
CVC_PAIRING_CONFIGURATIONS: tuple[tuple[int, ...], ...] = (
    (0, 1, 1, 1, 1),  # 1v4
    (0, 0, 0, 0, 1),  # 4v1
    (0, 0, 1, 1, 1),  # 2v3
    (0, 0, 0, 1, 1),  # 3v2
)
DEFAULT_CVC_SELF_PLAY_DESCRIPTION = "Self-play matches on CogsGuard Machina1"
DEFAULT_CVC_PAIRING_DESCRIPTION = (
    "Pairwise matchups on CogsGuard Machina1 with varied agent splits (1+4, 4+1, 2+3); "
    "scored by participation-weighted average"
)


class CvcSelfPlayReferee(SelfPlayRefereeBase):
    game = CVC_GAME
    description = DEFAULT_CVC_SELF_PLAY_DESCRIPTION


class CvcPairingReferee(PairingRefereeBase):
    game = CVC_GAME
    match_configurations = [list(config) for config in CVC_PAIRING_CONFIGURATIONS]
    description = DEFAULT_CVC_PAIRING_DESCRIPTION
