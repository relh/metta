from typing import Callable

from metta.app_backend.tournament.commissioners.base import CommissionerBase
from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.commissioners.beta_cogsguard import BetaCogsguardCommissioner
from metta.app_backend.tournament.commissioners.beta_cvc import BetaCvcCommissioner
from metta.app_backend.tournament.commissioners.beta_cvc_no_clips import BetaCvcNoClipsCommissioner
from metta.app_backend.tournament.commissioners.beta_test import BetaTestCommissioner

SEASONS: dict[str, Callable[[], CommissionerBase]] = {
    "beta": BetaCommissioner,
    "beta-cogsguard": BetaCogsguardCommissioner,
    "beta-cvc": BetaCvcCommissioner,
    "beta-cvc-no-clips": BetaCvcNoClipsCommissioner,
    "test-season": BetaTestCommissioner,
}

HIDDEN_SEASONS: list[str] = ["test-season", "beta"]

DEFAULT_SEASON: str = "beta-cvc"
