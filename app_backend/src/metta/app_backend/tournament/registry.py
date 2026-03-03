from metta.app_backend.tournament.commissioners.base import CommissionerBase
from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.commissioners.beta_cogsguard import BetaCogsguardCommissioner
from metta.app_backend.tournament.commissioners.beta_cvc import BetaCvcCommissioner
from metta.app_backend.tournament.commissioners.beta_cvc_no_clips import BetaCvcNoClipsCommissioner
from metta.app_backend.tournament.commissioners.beta_cvc_no_clips_no_vibes import BetaCvcNoClipsNoVibesCommissioner
from metta.app_backend.tournament.commissioners.beta_test import BetaTestCommissioner
from metta.app_backend.tournament.commissioners.teams.beta import BetaTeamsCommissioner
from metta.app_backend.tournament.commissioners.teams.small import (
    BetaTeamsSmallCommissioner,
    BetaTeamsTinyFixedCommissioner,
)
from metta.app_backend.tournament.settings import settings

_ENABLED_SEASON_COMMISSIONERS: list[type[CommissionerBase]] = [
    BetaCommissioner,
    BetaCogsguardCommissioner,
    BetaCvcCommissioner,
    BetaCvcNoClipsCommissioner,
    BetaCvcNoClipsNoVibesCommissioner,
    BetaTestCommissioner,
    BetaTeamsCommissioner,
    BetaTeamsSmallCommissioner,
    BetaTeamsTinyFixedCommissioner,
]


if settings.ENABLE_MOCK_TOURNAMENTS:
    from metta.app_backend.tournament.commissioners.teams.mock import MockTeamsCommissioner

    _ENABLED_SEASON_COMMISSIONERS.append(MockTeamsCommissioner)


SEASONS: dict[str, type[CommissionerBase]] = {c.season_name: c for c in _ENABLED_SEASON_COMMISSIONERS}
