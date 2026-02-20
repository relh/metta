from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from metta.app_backend.models.tournament import Pool, Season
from metta.app_backend.routes import tournament_routes
from metta.app_backend.tournament import registry as tournament_registry
from metta.app_backend.tournament.commissioners.base import CommissionerBase, MembershipChangeRequest
from metta.app_backend.tournament.commissioners.factory import build_commissioner
from metta.app_backend.tournament.referees.base import RefereeBase


class _DynamicCommissioner(CommissionerBase):
    season_name = "dynamic-season"
    referees = cast(dict[str, RefereeBase], {"dynamic-pool": object()})
    leaderboard_pool = "dynamic-pool"
    entry_pool = "dynamic-pool"

    def get_new_submission_membership_changes(self, policy_version_id: UUID) -> list[MembershipChangeRequest]:
        return []

    async def get_membership_changes(self, pools: dict[str, Pool]) -> list[MembershipChangeRequest]:
        return []


@pytest.mark.asyncio
async def test_build_commissioner_uses_live_registry_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tournament_registry, "SEASONS", {"dynamic-season": _DynamicCommissioner})
    commissioner = await build_commissioner("dynamic-season", season_id=uuid4())
    assert isinstance(commissioner, _DynamicCommissioner)


@pytest.mark.asyncio
async def test_resolve_season_uses_live_registry_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    seeded_season = Season(name="dynamic-season", canonical=True)
    monkeypatch.setattr(tournament_registry, "SEASONS", {"dynamic-season": _DynamicCommissioner})

    async def _fake_resolve_season(_session: object, _name: str, _version: int | None = None) -> Season:
        return seeded_season

    monkeypatch.setattr(tournament_routes, "resolve_season", _fake_resolve_season)
    season_name, season = await tournament_routes._resolve_season_or_404(
        cast(AsyncSession, object()),
        "dynamic-season",
    )
    assert season_name == "dynamic-season"
    assert season == seeded_season
