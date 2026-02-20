from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.referees.cogsguard import (
    CogsguardPairingReferee,
    CogsguardSelfPlayReferee,
)


class BetaCogsguardCommissioner(BetaCommissioner):
    season_name = "beta-cogsguard"
    display_name = "Beta CogsGuard"
    referees = {
        "qualifying": CogsguardSelfPlayReferee(),
        "competition": CogsguardPairingReferee(),
    }
    summary = "CogsGuard season: policies start in qualifying; promoted to competition if score meets threshold"
