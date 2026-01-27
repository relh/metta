"""TestCommissioner is a replica of BetaCommissioner intended for testing on the hidden test-season"""

from metta.app_backend.tournament.commissioners.beta import BetaCommissioner


class BetaTestCommissioner(BetaCommissioner):
    season_name = "test-season"
    summary = "Test season: policies handled exactly the same as with Beta, but get excluded from the Observatory UI."
