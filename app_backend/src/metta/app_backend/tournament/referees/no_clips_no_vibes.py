from metta.app_backend.tournament.referees.envs import get_game
from metta.app_backend.tournament.referees.pairing import PairingRefereeBase
from metta.app_backend.tournament.referees.selfplay import SelfPlayRefereeBase

NO_CLIPS_NO_VIBES_GAME = get_game("cogsguard_machina_1_no_clips_no_vibes_8agents")
NO_CLIPS_NO_VIBES_PAIRING_CONFIGURATIONS: tuple[tuple[int, ...], ...] = (
    (0, 0, 1, 1, 1, 1, 1, 1),  # 2v6
    (0, 0, 0, 0, 0, 0, 1, 1),  # 6v2
    (0, 0, 0, 0, 1, 1, 1, 1),  # 4v4
)


class NoClipsNoVibesSelfPlayReferee(SelfPlayRefereeBase):
    game = NO_CLIPS_NO_VIBES_GAME
    description = "Self-play matches on CogsGuard Machina1 (8 agents, clips and vibe changing disabled)"


class NoClipsNoVibesPairingReferee(PairingRefereeBase):
    game = NO_CLIPS_NO_VIBES_GAME
    match_configurations = [list(config) for config in NO_CLIPS_NO_VIBES_PAIRING_CONFIGURATIONS]
    description = (
        "Pairwise matchups on CogsGuard Machina1 with 8 agents (2+6, 6+2, 4+4), clips and vibe changing "
        "disabled; scored by participation-weighted average"
    )
