from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.referees.cvc import (
    CvcPairingReferee,
    CvcSelfPlayReferee,
)


class BetaCvcCommissioner(BetaCommissioner):
    season_name = "beta-cvc"
    referees = {
        "qualifying": CvcSelfPlayReferee(),
        "competition": CvcPairingReferee(),
    }
    summary = "CvC season: policies start in qualifying; promoted to competition if score meets threshold"
    validation_mission = "cogsguard_machina_1"
    promotion_min_score = 0.05
