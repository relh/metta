from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vibeservatory.backend.dashboard_backend.role_stats.router as role_stats_router
from vibeservatory.backend.dashboard_backend.config import settings
from vibeservatory.backend.dashboard_backend.role_stats.router import create_role_stats_router


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")
    app = FastAPI()
    app.include_router(create_role_stats_router())
    return TestClient(app, base_url="http://localhost")


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {
        "X-Auth-Secret": "test-secret",
        "X-User-Id": "regular-user",
        "X-User-Email": "regular@example.com",
        "X-User-Is-Softmax-Team-Member": "false",
    }


def test_role_definitions_require_authentication(client: TestClient) -> None:
    response = client.get("/stats/roles/definitions")
    assert response.status_code == 401


def test_role_definitions_include_death_metric(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/stats/roles/definitions", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    for role in ("miner", "scout", "scrambler", "aligner"):
        role_metrics = body["roles"][role]
        death = next((metric for metric in role_metrics if metric["key"] == "death"), None)
        assert death is not None
        assert death["source_names"] == ["death"]


def test_role_percentiles_return_rows(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updated_at = datetime(2026, 3, 5, 0, 0, tzinfo=UTC)

    async def fake_compute_policy_role_percentiles(_pool_id, _policy_version_id):
        return [
            SimpleNamespace(
                role="miner",
                percentile=91.2,
                details={"metrics": {"miner.gained": {"avg": 1.0}}},
                updated_at=updated_at,
            )
        ]

    monkeypatch.setattr(role_stats_router, "compute_policy_role_percentiles", fake_compute_policy_role_percentiles)

    response = client.get(
        f"/stats/roles/pools/{uuid4()}/policy-versions/{uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == [
        {
            "role": "miner",
            "percentile": 91.2,
            "details": {"metrics": {"miner.gained": {"avg": 1.0}}},
            "updated_at": "2026-03-05T00:00:00Z",
        }
    ]


def test_role_percentiles_404_when_empty(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_compute_policy_role_percentiles(_pool_id, _policy_version_id):
        return []

    monkeypatch.setattr(role_stats_router, "compute_policy_role_percentiles", fake_compute_policy_role_percentiles)

    response = client.get(
        f"/stats/roles/pools/{uuid4()}/policy-versions/{uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_role_leaderboard_rejects_unknown_role(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(
        f"/stats/roles/pools/{uuid4()}/roles/not-a-role/leaderboard",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_role_leaderboard_clamps_limit(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_limit: list[int] = []
    policy_version_id = uuid4()
    updated_at = datetime(2026, 3, 5, 0, 0, tzinfo=UTC)

    async def fake_compute_role_leaderboard(_pool_id, _role, limit: int):
        captured_limit.append(limit)
        return [
            SimpleNamespace(
                rank=1,
                policy_version_id=policy_version_id,
                policy_name="alpha-policy",
                policy_version=7,
                percentile=99.0,
                details={"metrics": {}},
                updated_at=updated_at,
            )
        ]

    monkeypatch.setattr(role_stats_router, "compute_role_leaderboard", fake_compute_role_leaderboard)

    response = client.get(
        f"/stats/roles/pools/{uuid4()}/roles/miner/leaderboard?limit=99999",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert captured_limit == [500]
    assert response.json() == [
        {
            "rank": 1,
            "policy_version_id": str(policy_version_id),
            "policy_name": "alpha-policy",
            "policy_version": 7,
            "percentile": 99.0,
            "details": {"metrics": {}},
            "updated_at": "2026-03-05T00:00:00Z",
        }
    ]
