from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from metta.app_backend.models.tournament import Season
from metta.app_backend.tournament.commissioners.base import CommissionerBase


class _StubCommissioner(CommissionerBase):
    season_name = "test-season"
    display_name = "Test Season"
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


async def _run_n_iterations(
    commissioner: _StubCommissioner,
    n: int,
    *,
    season: Season | None,
    server_compat: str = "0.3",
):
    iteration = 0
    in_db_session = False
    sleep_while_in_db: list[bool] = []
    commissioner.season_id = season.id if season is not None else uuid4()

    async def fake_sleep(_):
        sleep_while_in_db.append(in_db_session)
        nonlocal iteration
        iteration += 1
        if iteration >= n:
            raise _StopLoop

    class _StopLoop(Exception):
        pass

    @asynccontextmanager
    async def fake_db_session(*_, **__):
        nonlocal in_db_session
        in_db_session = True
        try:
            yield MagicMock()
        finally:
            in_db_session = False

    with (
        patch.object(commissioner, "_ensure_season_exists", new_callable=AsyncMock),
        patch.object(commissioner, "_resolve_target_season", new_callable=AsyncMock, return_value=season),
        patch.object(commissioner, "_run_cycle", new_callable=AsyncMock, return_value=False),
        patch("metta.app_backend.tournament.commissioners.base.db_session", fake_db_session),
        patch("metta.app_backend.tournament.commissioners.base.asyncio.sleep", side_effect=fake_sleep) as mock_sleep,
        patch("metta.app_backend.tournament.commissioners.base.get_compat_version", return_value=server_compat),
    ):
        with pytest.raises(_StopLoop):
            await commissioner.run()
        return mock_sleep, commissioner._run_cycle, sleep_while_in_db


@pytest.mark.asyncio
async def test_server_compat_mismatch_skips_cycle():
    """Season requires 0.4 but server has 0.3 installed — skip to avoid incompatible env configs."""
    commissioner = _StubCommissioner(season_id=uuid4())
    season = _make_season(compat_version="0.4")
    _, mock_run_cycle, sleep_while_in_db = await _run_n_iterations(commissioner, 1, season=season, server_compat="0.3")
    mock_run_cycle.assert_not_called()
    assert sleep_while_in_db == [False]


@pytest.mark.asyncio
async def test_server_compat_match_runs_cycle():
    commissioner = _StubCommissioner(season_id=uuid4())
    season = _make_season(compat_version="0.3")
    _, mock_run_cycle, _ = await _run_n_iterations(commissioner, 1, season=season, server_compat="0.3")
    mock_run_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_compat_none_runs_cycle():
    commissioner = _StubCommissioner(season_id=uuid4())
    season = _make_season(compat_version=None)
    _, mock_run_cycle, _ = await _run_n_iterations(commissioner, 1, season=season, server_compat="0.3")
    mock_run_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_disabled_season_sleeps_outside_db_session():
    commissioner = _StubCommissioner(season_id=uuid4())
    season = _make_season(disabled_at=datetime.now(UTC))
    _, mock_run_cycle, sleep_while_in_db = await _run_n_iterations(commissioner, 1, season=season)
    mock_run_cycle.assert_not_called()
    assert sleep_while_in_db == [False]
