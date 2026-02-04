import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import Connection

from metta.app_backend.migrations import MIGRATIONS
from metta.app_backend.schema_manager import run_migrations


class BaseAsyncTest:
    @pytest.fixture(scope="function")
    def stats_repo(self, db_uri: str) -> str:
        from metta.app_backend import config as app_config  # noqa: PLC0415
        from metta.app_backend import database  # noqa: PLC0415

        database._engine = None
        database._session_factory = None
        app_config.settings.STATS_DB_URI = db_uri

        with Connection.connect(db_uri) as con:
            run_migrations(con, MIGRATIONS)

        return db_uri

    @pytest.fixture(scope="function")
    def test_app(self, stats_repo: str) -> FastAPI:
        _ = stats_repo
        from metta.app_backend.server import create_app  # noqa: PLC0415

        return create_app()

    @pytest.fixture(scope="function")
    def test_client(self, test_app: FastAPI) -> TestClient:
        return TestClient(test_app)
