from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.referees.no_clips_no_vibes import (
    NoClipsNoVibesPairingReferee,
    NoClipsNoVibesSelfPlayReferee,
)


class BetaCvcNoClipsNoVibesCommissioner(BetaCommissioner):
    season_name = "beta-cvc-no-clips-no-vibes"
    referees = {
        "qualifying": NoClipsNoVibesSelfPlayReferee(),
        "competition": NoClipsNoVibesPairingReferee(),
    }
    summary = (
        "No-clips-no-vibes season: CogsGuard with clips and vibe changing disabled; "
        "policies qualify then compete head-to-head"
    )
    promotion_min_score = 0.05
