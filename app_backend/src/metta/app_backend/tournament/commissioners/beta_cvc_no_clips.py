from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.referees.no_clips import NoClipsPairingReferee, NoClipsSelfPlayReferee


class BetaCvcNoClipsCommissioner(BetaCommissioner):
    season_name = "beta-cvc-no-clips"
    compat_version = "0.5"
    referees = {
        "qualifying": NoClipsSelfPlayReferee(),
        "competition": NoClipsPairingReferee(),
    }
    summary = "No-clips season: CogsGuard with clips disabled; policies qualify then compete head-to-head"
    promotion_min_score = 0.05
