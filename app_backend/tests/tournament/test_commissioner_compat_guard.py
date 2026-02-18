from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from metta.app_backend.models.tournament import Season
from metta.app_backend.tournament.commissioners.base import CommissionerBase


class _StubCommissioner(CommissionerBase):
    season_name = "test-season"
    referees: dict = {}
    leaderboard_pool = None  # type: ignore[assignment]
    entry_pool = None  # type: ignore[assignment]

    def get_new_submission_membership_changes(self, policy_version_id):
        return []

    async def get_membership_changes(self, pools):
        return []


def _make_season(*, compat_version: str | None = None, disabled_at=None) -> Season:
    return Season(
        id=uuid4(),
        name="test-season",
        version=1,
        canonical=True,
        compat_version=compat_version,
        disabled_at=disabled_at,
    )


def _make_mock_session(season: Season | None):
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = season
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def fake_db_session():
        yield mock_session

    return fake_db_session


async def _run_n_iterations(
    commissioner: _StubCommissioner,
    n: int,
    *,
    season: Season | None,
):
    iteration = 0

    async def fake_sleep(_):
        nonlocal iteration
        iteration += 1
        if iteration >= n:
            raise _StopLoop

    class _StopLoop(Exception):
        pass

    with (
        patch.object(commissioner, "_ensure_season_exists", new_callable=AsyncMock),
        patch.object(commissioner, "_run_cycle", new_callable=AsyncMock, return_value=False),
        patch("metta.app_backend.tournament.commissioners.base.db_session", _make_mock_session(season)),
        patch("metta.app_backend.tournament.commissioners.base.asyncio.sleep", side_effect=fake_sleep) as mock_sleep,
    ):
        with pytest.raises(_StopLoop):
            await commissioner.run()
        return mock_sleep, commissioner._run_cycle


@pytest.mark.asyncio
async def test_compat_mismatch_skips_cycle():
    commissioner = _StubCommissioner()
    commissioner.compat_version = "0.3"
    season = _make_season(compat_version="0.2")
    _, mock_run_cycle = await _run_n_iterations(commissioner, 1, season=season)
    mock_run_cycle.assert_not_called()


@pytest.mark.asyncio
async def test_compat_match_runs_cycle():
    commissioner = _StubCommissioner()
    commissioner.compat_version = "0.2"
    season = _make_season(compat_version="0.2")
    _, mock_run_cycle = await _run_n_iterations(commissioner, 1, season=season)
    mock_run_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_compat_none_runs_cycle():
    commissioner = _StubCommissioner()
    commissioner.compat_version = "0.3"
    season = _make_season(compat_version=None)
    _, mock_run_cycle = await _run_n_iterations(commissioner, 1, season=season)
    mock_run_cycle.assert_called_once()
