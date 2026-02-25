from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from metta.app_backend.models.tournament import Season
from metta.app_backend.tournament.cli import _seed_missing_seasons, _supervisor_loop

MODULE = "metta.app_backend.tournament.cli"


def _make_season(name: str = "beta", *, canonical: bool = True, disabled_at=None) -> Season:
    return Season(
        id=uuid4(),
        name=name,
        version=1,
        canonical=canonical,
        disabled_at=disabled_at,
    )


class _StopLoop(Exception):
    pass


@pytest.mark.asyncio
async def test_supervisor_starts_known_seasons():
    season = _make_season("beta")
    mock_commissioner = MagicMock()
    mock_commissioner.run = AsyncMock()

    iteration = 0

    async def fake_sleep(_):
        nonlocal iteration
        iteration += 1
        if iteration >= 1:
            raise _StopLoop

    @asynccontextmanager
    async def fake_db_session(*_, **__):
        yield MagicMock()

    with (
        patch(f"{MODULE}._seed_missing_seasons", new_callable=AsyncMock),
        patch(f"{MODULE}.db_session", fake_db_session),
        patch(f"{MODULE}._query_live_seasons", new_callable=AsyncMock, return_value=[season]) as mock_query,
        patch(f"{MODULE}.SEASONS", {"beta": MagicMock()}),
        patch(f"{MODULE}.build_commissioner", new_callable=AsyncMock, return_value=mock_commissioner) as mock_build,
        patch(f"{MODULE}.asyncio.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(_StopLoop):
            await _supervisor_loop()

        mock_query.assert_called_once()
        mock_build.assert_called_once_with("beta", season_id=season.id)
        mock_commissioner.run.assert_called_once()


@pytest.mark.asyncio
async def test_supervisor_skips_unknown_season_names():
    season = _make_season("unknown")

    iteration = 0

    async def fake_sleep(_):
        nonlocal iteration
        iteration += 1
        if iteration >= 1:
            raise _StopLoop

    @asynccontextmanager
    async def fake_db_session(*_, **__):
        yield MagicMock()

    with (
        patch(f"{MODULE}._seed_missing_seasons", new_callable=AsyncMock),
        patch(f"{MODULE}.db_session", fake_db_session),
        patch(f"{MODULE}._query_live_seasons", new_callable=AsyncMock, return_value=[season]),
        patch(f"{MODULE}.SEASONS", {"beta": MagicMock()}),
        patch(f"{MODULE}.build_commissioner", new_callable=AsyncMock) as mock_build,
        patch(f"{MODULE}.asyncio.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(_StopLoop):
            await _supervisor_loop()

        mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_supervisor_cleans_up_exited_commissioners():
    season = _make_season("beta")
    mock_commissioner = MagicMock()
    mock_commissioner.run = AsyncMock(return_value=None)

    iteration = 0

    real_sleep = asyncio.sleep

    async def fake_sleep(_):
        nonlocal iteration
        await real_sleep(0)
        iteration += 1
        if iteration >= 2:
            raise _StopLoop

    @asynccontextmanager
    async def fake_db_session(*_, **__):
        yield MagicMock()

    build_count = 0

    async def fake_build(name, *, season_id):
        nonlocal build_count
        build_count += 1
        comm = MagicMock()
        comm.run = AsyncMock(return_value=None)
        return comm

    with (
        patch(f"{MODULE}._seed_missing_seasons", new_callable=AsyncMock),
        patch(f"{MODULE}.db_session", fake_db_session),
        patch(f"{MODULE}._query_live_seasons", new_callable=AsyncMock, return_value=[season]),
        patch(f"{MODULE}.SEASONS", {"beta": MagicMock()}),
        patch(f"{MODULE}.build_commissioner", side_effect=fake_build),
        patch(f"{MODULE}.asyncio.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(_StopLoop):
            await _supervisor_loop()

        assert build_count == 2


@pytest.mark.asyncio
async def test_supervisor_handles_cancelled_tasks():
    season = _make_season("beta")
    mock_commissioner = MagicMock()
    cancelled_future: asyncio.Future[None] = asyncio.get_event_loop().create_future()
    cancelled_future.cancel()
    mock_commissioner.run = AsyncMock(return_value=None)

    iteration = 0
    real_sleep = asyncio.sleep

    async def fake_sleep(_):
        nonlocal iteration
        await real_sleep(0)
        iteration += 1
        if iteration >= 2:
            raise _StopLoop

    @asynccontextmanager
    async def fake_db_session(*_, **__):
        yield MagicMock()

    build_count = 0

    async def fake_build(name, *, season_id):
        nonlocal build_count
        build_count += 1
        comm = MagicMock()
        if build_count == 1:
            comm.run = AsyncMock(side_effect=asyncio.CancelledError)
        else:
            comm.run = AsyncMock(return_value=None)
        return comm

    with (
        patch(f"{MODULE}._seed_missing_seasons", new_callable=AsyncMock),
        patch(f"{MODULE}.db_session", fake_db_session),
        patch(f"{MODULE}._query_live_seasons", new_callable=AsyncMock, return_value=[season]),
        patch(f"{MODULE}.SEASONS", {"beta": MagicMock()}),
        patch(f"{MODULE}.build_commissioner", side_effect=fake_build),
        patch(f"{MODULE}.asyncio.sleep", side_effect=fake_sleep),
    ):
        with pytest.raises(_StopLoop):
            await _supervisor_loop()

        assert build_count == 2


@pytest.mark.asyncio
async def test_seed_missing_seasons_creates_absent_rows():
    mock_cls = MagicMock()
    mock_cls.season_name = "beta"
    mock_cls.initial_compat_version = "42"
    mock_cls.get_initial_season_fields.return_value = {}

    created_seasons: list[Season] = []

    @asynccontextmanager
    async def fake_db_session(*_, **__):
        mock_session = MagicMock(spec=AsyncSession)

        async def fake_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = AsyncMock(side_effect=fake_execute)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        def capture_add(obj):
            if isinstance(obj, Season):
                created_seasons.append(obj)

        mock_session.add = capture_add
        yield mock_session

    with (
        patch(f"{MODULE}.db_session", fake_db_session),
        patch(f"{MODULE}.SEASONS", {"beta": mock_cls}),
    ):
        await _seed_missing_seasons()

    assert len(created_seasons) == 1
    assert created_seasons[0].name == "beta"
    assert created_seasons[0].canonical is True
    assert created_seasons[0].compat_version == "42"
