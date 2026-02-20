from contextlib import asynccontextmanager

import pytest

from metta.app_backend import database


@pytest.mark.asyncio
async def test_with_db_default_uses_write_session(monkeypatch: pytest.MonkeyPatch):
    read_only_calls: list[bool] = []

    @asynccontextmanager
    async def fake_db_session(read_only: bool = False):
        read_only_calls.append(read_only)
        yield None

    monkeypatch.setattr(database, "db_session", fake_db_session)

    @database.with_db
    async def _fn() -> str:
        return "ok"

    assert await _fn() == "ok"
    assert read_only_calls == [False]


@pytest.mark.asyncio
async def test_with_db_read_only_routes_read_only_session(monkeypatch: pytest.MonkeyPatch):
    read_only_calls: list[bool] = []

    @asynccontextmanager
    async def fake_db_session(read_only: bool = False):
        read_only_calls.append(read_only)
        yield None

    monkeypatch.setattr(database, "db_session", fake_db_session)

    @database.with_db(read_only=True)
    async def _fn() -> str:
        return "ok"

    assert await _fn() == "ok"
    assert read_only_calls == [True]


def test_read_only_engine_uses_read_only_uri():
    original_write_uri = database.settings.STATS_DB_URI
    original_read_only_uri = database.settings.STATS_DB_READ_ONLY_URI
    try:
        database._engine = None
        database._read_only_engine = None
        database._session_factory = None
        database._read_only_session_factory = None

        database.settings.STATS_DB_URI = "postgresql://writer:pw@writer.example/metta"
        database.settings.STATS_DB_READ_ONLY_URI = "postgresql://reader:pw@reader.example/metta"

        read_only_engine = database._get_engine(read_only=True)
        write_engine = database._get_engine(read_only=False)

        assert "reader.example" in str(read_only_engine.url)
        assert "writer.example" in str(write_engine.url)
    finally:
        database._engine = None
        database._read_only_engine = None
        database._session_factory = None
        database._read_only_session_factory = None
        database.settings.STATS_DB_URI = original_write_uri
        database.settings.STATS_DB_READ_ONLY_URI = original_read_only_uri


def test_read_only_engine_reuses_write_engine_when_read_only_uri_unset():
    original_write_uri = database.settings.STATS_DB_URI
    original_read_only_uri = database.settings.STATS_DB_READ_ONLY_URI
    try:
        database._engine = None
        database._read_only_engine = None
        database._session_factory = None
        database._read_only_session_factory = None

        database.settings.STATS_DB_URI = "postgresql://writer:pw@writer.example/metta"
        database.settings.STATS_DB_READ_ONLY_URI = None

        read_only_engine = database._get_engine(read_only=True)
        write_engine = database._get_engine(read_only=False)

        assert read_only_engine is write_engine
        assert database._read_only_engine is None
    finally:
        database._engine = None
        database._read_only_engine = None
        database._session_factory = None
        database._read_only_session_factory = None
        database.settings.STATS_DB_URI = original_write_uri
        database.settings.STATS_DB_READ_ONLY_URI = original_read_only_uri
