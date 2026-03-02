from uuid import uuid4

from metta.app_backend.routes.tournament_routes import _extract_game_description
from metta.app_backend.tournament.commissioners.base import CommissionerBase
from metta.app_backend.tournament.referees.base import RefereeBase
from metta.app_backend.tournament.referees.envs import get_game
from metta.app_backend.tournament.referees.selfplay import SelfPlayReferee


def _make_referee(env_name: str) -> SelfPlayReferee:
    ref = SelfPlayReferee()
    ref.game = get_game(env_name)
    return ref


class _VersionedCommissioner(CommissionerBase):
    season_name = "test-versioned"
    display_name = "Test Versioned"
    referees: dict[str, RefereeBase] = {"pool": _make_referee("cogsguard_4agents")}  # type: ignore[assignment]
    leaderboard_pool = "pool"
    entry_pool = "pool"
    summary = ""

    def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self._v1_referees: dict[str, RefereeBase] = {"pool": _make_referee("cogsguard_4agents")}
        self._v2_referees: dict[str, RefereeBase] = {"pool": _make_referee("cogsguard_machina_1_no_clips_8agents")}

    def get_referees(self, season_version: int) -> dict[str, RefereeBase]:
        if season_version >= 2:
            return self._v2_referees
        return self._v1_referees

    def get_new_submission_membership_changes(self, policy_version_id):  # type: ignore[override]
        return []

    async def get_membership_changes(self, pools):  # type: ignore[override]
        return []


def test_extract_game_description_uses_versioned_referees() -> None:
    commissioner = _VersionedCommissioner(season_id=uuid4())
    v1_desc = _extract_game_description(commissioner, 1)
    v2_desc = _extract_game_description(commissioner, 2)
    assert v1_desc
    assert v2_desc
    assert v1_desc != v2_desc
    assert "Variant" not in v1_desc
    assert "Variant" in v2_desc
