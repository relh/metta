from typing import Callable

from metta.app_backend.tournament.commissioners.base import CommissionerBase
from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.commissioners.beta_cogsguard import BetaCogsguardCommissioner

SEASONS: dict[str, Callable[[], CommissionerBase]] = {
    "beta": BetaCommissioner,
    "beta-cogsguard": BetaCogsguardCommissioner,
}
