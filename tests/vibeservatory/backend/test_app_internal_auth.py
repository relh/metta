from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import metta.app_backend.database as app_db
from vibeservatory.backend.dashboard_backend import app as dashboard_app
from vibeservatory.backend.dashboard_backend import database as dashboard_db
from vibeservatory.backend.dashboard_backend.config import settings


def _reset_dashboard_db_side_effects() -> None:
    dashboard_db._CONFIGURED = False
    app_db.db_session = dashboard_db._ORIGINAL_DB_SESSION
    app_db._engine = None
    app_db._read_only_engine = None
    app_db._session_factory = None
    app_db._read_only_session_factory = None


_reset_dashboard_db_side_effects()


@pytest.fixture(autouse=True)
def reset_dashboard_db_state() -> Iterator[None]:
    _reset_dashboard_db_side_effects()
    yield
    _reset_dashboard_db_side_effects()


@pytest.mark.parametrize("path", ["/internal/docs", "/internal/openapi.json"])
def test_internal_routes_require_auth(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")

    client = TestClient(dashboard_app.create_app(), base_url="http://localhost")
    response = client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/internal/docs", "/internal/openapi.json"])
def test_internal_routes_allow_softmax_users(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")

    client = TestClient(dashboard_app.create_app(), base_url="http://localhost")
    response = client.get(
        path,
        headers={
            "X-Auth-Secret": "test-secret",
            "X-User-Id": "softmax-user",
            "X-User-Email": "softmax@softmax.com",
            "X-User-Is-Softmax-Team-Member": "true",
        },
    )
    assert response.status_code == 200
