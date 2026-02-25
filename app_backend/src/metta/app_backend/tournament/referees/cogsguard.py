from metta.app_backend.tournament.referees.envs import get_game
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase

COGSGUARD_GAME = get_game("cogsguard_10agents")
COGSGUARD_PAIRING_CONFIGURATIONS: tuple[tuple[int, ...], ...] = (
    (0, 1, 1, 1, 1, 1, 1, 1, 1, 1),  # 1v9
    (0, 0, 0, 0, 0, 0, 0, 0, 0, 1),  # 9v1
    (0, 0, 0, 0, 0, 1, 1, 1, 1, 1),  # 5v5
)


class CogsguardSelfPlayReferee(SelfPlayRefereeBase):
    game = COGSGUARD_GAME
    description = "Self-play matches on CogsGuard Machina1"


class CogsguardPairingReferee(PairingRefereeBase):
    game = COGSGUARD_GAME
    match_configurations = [list(config) for config in COGSGUARD_PAIRING_CONFIGURATIONS]
    description = (
        "Pairwise matchups on CogsGuard Machina1 with varied agent splits (1+9, 9+1, 5+5); "
        "scored by participation-weighted average"
    )
