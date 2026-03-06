from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibeservatory.backend.dashboard_backend.chatprop.router import create_chatprop_router
from vibeservatory.backend.dashboard_backend.config import settings


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/chatprop/api/catalog"),
        ("POST", "/chatprop/api/analysis/context"),
    ],
)
def test_chatprop_api_requires_auth(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")

    app = FastAPI()
    app.include_router(create_chatprop_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.request(method, path)
    assert response.status_code == 401


def test_chatprop_api_rejects_non_softmax_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")

    app = FastAPI()
    app.include_router(create_chatprop_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get(
        "/chatprop/api/catalog",
        headers={
            "X-Auth-Secret": "test-secret",
            "X-User-Id": "regular-user",
            "X-User-Email": "regular@example.com",
            "X-User-Is-Softmax-Team-Member": "false",
        },
    )
    assert response.status_code == 403


def test_chatprop_api_allows_softmax_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")

    app = FastAPI()
    app.include_router(create_chatprop_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get(
        "/chatprop/api/health",
        headers={
            "X-Auth-Secret": "test-secret",
            "X-User-Id": "softmax-user",
            "X-User-Email": "softmax@softmax.com",
            "X-User-Is-Softmax-Team-Member": "true",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
