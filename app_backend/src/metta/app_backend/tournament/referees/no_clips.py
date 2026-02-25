from metta.app_backend.tournament.referees.envs import get_game
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase

NO_CLIPS_GAME = get_game("cogsguard_machina_1_no_clips_8agents")
NO_CLIPS_PAIRING_CONFIGURATIONS: tuple[tuple[int, ...], ...] = (
    (0, 0, 1, 1, 1, 1, 1, 1),  # 2v6
    (0, 0, 0, 0, 0, 0, 1, 1),  # 6v2
    (0, 0, 0, 0, 1, 1, 1, 1),  # 4v4
)


class NoClipsSelfPlayReferee(SelfPlayRefereeBase):
    game = NO_CLIPS_GAME
    description = "Self-play matches on CogsGuard Machina1 (8 agents, clips disabled)"


class NoClipsPairingReferee(PairingRefereeBase):
    game = NO_CLIPS_GAME
    match_configurations = [list(config) for config in NO_CLIPS_PAIRING_CONFIGURATIONS]
    description = (
        "Pairwise matchups on CogsGuard Machina1 with 8 agents (2+6, 6+2, 4+4), clips disabled; "
        "scored by participation-weighted average"
    )
