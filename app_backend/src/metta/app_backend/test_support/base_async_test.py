"""Base class for tests requiring function-scoped async fixtures."""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from metta.app_backend.metta_repo import MettaRepo


class BaseAsyncTest:
    """Base class for tests that require function-scoped async fixtures.

    This base class provides function-scoped fixtures for test classes that:
    - Need proper async cleanup of database connections after each test
    - Test concurrent async operations requiring fresh connections
    - Contain async tests that directly interact with the database

    Using function scope ensures test isolation and prevents connection pool issues.
    """

    @pytest_asyncio.fixture(scope="function")
    async def stats_repo(self, db_uri: str) -> AsyncGenerator[MettaRepo, None]:
        """Create a MettaRepo instance with async cleanup for the test database."""
        from metta.app_backend import config as app_config  # noqa: PLC0415
        from metta.app_backend import database  # noqa: PLC0415

        database._engine = None
        database._session_factory = None
        app_config.settings.STATS_DB_URI = db_uri

        repo = MettaRepo(db_uri)
        yield repo
        # Ensure pool is closed gracefully
        if repo._pool is not None:
            try:
                await repo._pool.close()
            except (RuntimeError, asyncio.CancelledError):
                # Event loop might be closed or tasks cancelled, ignore
                pass

    @pytest.fixture(scope="function")
    def test_app(self, stats_repo: MettaRepo) -> FastAPI:
        """Create a test FastAPI app. stats_repo configures the global DB settings."""
        _ = stats_repo
        from metta.app_backend.server import create_app  # noqa: PLC0415

        return create_app()

    @pytest.fixture(scope="function")
    def test_client(self, test_app: FastAPI) -> TestClient:
        """Create a test client."""
        return TestClient(test_app)
