from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.referees.base import RefereeBase
from metta.app_backend.tournament.referees.cvc import (
    CvcPairingReferee,
    CvcSelfPlayReferee,
)


class _CvcSelfPlayV2(CvcSelfPlayReferee):
    num_agents: int = 8
    description: str = "Self-play matches on CogsGuard Machina1 (8 agents)"


class _CvcPairingV2(CvcPairingReferee):
    num_agents: int = 8
    match_configurations: list[list[int]] = [
        [0, 0, 1, 1, 1, 1, 1, 1],  # 2v6
        [0, 0, 0, 0, 0, 0, 1, 1],  # 6v2
        [0, 0, 0, 0, 1, 1, 1, 1],  # 4v4
    ]
    description: str = (
        "Pairwise matchups on CogsGuard Machina1 with 8 agents (2+6, 6+2, 4+4); "
        "scored by participation-weighted average"
    )


class BetaCvcCommissioner(BetaCommissioner):
    season_name = "beta-cvc"
    display_name = "Beta CvC"
    referees = {
        "qualifying": CvcSelfPlayReferee(),
        "competition": CvcPairingReferee(),
    }
    _v2_referees: dict[str, RefereeBase] = {
        "qualifying": _CvcSelfPlayV2(),
        "competition": _CvcPairingV2(),
    }
    summary = "CvC season: policies start in qualifying; promoted to competition if score meets threshold"
    promotion_min_score = 0.05

    def get_referees(self, season_version: int) -> dict[str, RefereeBase]:
        if season_version >= 2:
            return self._v2_referees
        return self.referees
