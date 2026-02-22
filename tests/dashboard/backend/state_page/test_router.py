from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from dashboard.backend.dashboard_backend.state_page.router import create_dashboard_router


class _ScalarsResult:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return self._values


class _ExecuteResult:
    def __init__(self, *, scalar: Any | None = None, scalar_values: list[Any] | None = None) -> None:
        self._scalar = scalar
        self._scalar_values = scalar_values or []

    def scalar_one_or_none(self) -> Any | None:
        return self._scalar

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._scalar_values)


class _FakeSession:
    def __init__(self, results: list[_ExecuteResult]) -> None:
        self._results = results

    async def execute(self, _query: Any) -> _ExecuteResult:
        assert self._results, "Unexpected query execution"
        return self._results.pop(0)


def test_dashboard_data_builds_commissioner_with_season_id(
    monkeypatch: Any,
) -> None:
    policy_version_id = uuid4()
    season_id = uuid4()
    policy_id = uuid4()

    fake_policy_version = SimpleNamespace(
        id=policy_version_id,
        version=3,
        policy_id=policy_id,
        policy=SimpleNamespace(name="gimpy"),
    )
    fake_season = SimpleNamespace(
        id=season_id,
        name="beta-teams-large",
        canonical=True,
        version=7,
    )

    async def fake_require_policy_version(_policy_version_id: str) -> tuple[Any, Any]:
        return policy_version_id, fake_policy_version

    async def fake_fetch_sources(_policy_version_id: Any, _limit: int) -> tuple[list[Any], list[Any]]:
        return [], []

    async def fake_build_sorted_dashboard_episodes(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    calls: list[tuple[str, Any]] = []

    class _FakeCommissioner:
        async def get_leaderboard(self, pool_name: str | None = None) -> list[tuple[Any, float, int]]:
            calls.append(("get_leaderboard", pool_name))
            return [(policy_version_id, 1.23, 9)]

    async def fake_build_commissioner(season_name: str, *, season_id: Any) -> _FakeCommissioner:
        calls.append((season_name, season_id))
        return _FakeCommissioner()

    @asynccontextmanager
    async def fake_db_session(*, read_only: bool = False) -> Any:
        assert read_only
        session = _FakeSession(
            [
                _ExecuteResult(scalar=fake_season),
                _ExecuteResult(scalar=None),
                _ExecuteResult(scalar_values=[]),
            ]
        )
        yield session

    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router._require_policy_version",
        fake_require_policy_version,
    )
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router._fetch_policy_dashboard_sources",
        fake_fetch_sources,
    )
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router._build_sorted_dashboard_episodes",
        fake_build_sorted_dashboard_episodes,
    )
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router.build_commissioner",
        fake_build_commissioner,
    )
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router.db_session",
        fake_db_session,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get(f"/dashboard/v1/policies/versions/{policy_version_id}/data")

    assert response.status_code == 200
    assert calls[0] == ("beta-teams-large", season_id)
    assert calls[1] == ("get_leaderboard", None)
    payload = response.json()
    derived = payload["derived"]
    assert "unsupported" in derived
    assert "instrumentation" in derived
    assert "stats_inventory" in derived
    assert "actions" in derived
    assert "orchestration" in derived


def test_role_percentiles_uses_first_pool_with_data(monkeypatch: Any) -> None:
    policy_version_id = uuid4()
    first_pool_id = uuid4()
    second_pool_id = uuid4()

    fake_policy_version = SimpleNamespace(
        id=policy_version_id,
        version=3,
        policy_id=uuid4(),
        policy=SimpleNamespace(name="gimpy"),
    )
    first_pool = SimpleNamespace(id=first_pool_id, name="competition")
    second_pool = SimpleNamespace(id=second_pool_id, name="qualifying")

    async def fake_require_policy_version(_policy_version_id: str) -> tuple[Any, Any]:
        return policy_version_id, fake_policy_version

    @asynccontextmanager
    async def fake_db_session(*, read_only: bool = False) -> Any:
        assert read_only
        yield SimpleNamespace()

    async def fake_candidate_role_pools_for_policy(_session: Any, _policy_version_id: Any) -> list[Any]:
        return [first_pool, second_pool]

    async def fake_compute_policy_role_percentiles(pool_id: Any, _policy_version_id: Any) -> list[Any]:
        if pool_id == first_pool_id:
            return []
        return [
            SimpleNamespace(
                role="miner",
                percentile=77.0,
                details={
                    "metrics": {
                        "miner.gained": {
                            "avg": 4.2,
                            "percentile": 77.0,
                            "higher_is_better": True,
                            "samples": 12,
                            "source_names": ["miner.gained"],
                            "source_metrics": {"miner.gained": {"avg": 4.2, "samples": 12}},
                        }
                    },
                    "overall_percentile": 77.0,
                },
                updated_at=datetime.now(UTC),
            )
        ]

    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router._require_policy_version",
        fake_require_policy_version,
    )
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router.db_session",
        fake_db_session,
    )
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router._candidate_role_pools_for_policy",
        fake_candidate_role_pools_for_policy,
    )
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router.compute_policy_role_percentiles",
        fake_compute_policy_role_percentiles,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get(f"/dashboard/v1/policies/versions/{policy_version_id}/role-percentiles")
    assert response.status_code == 200
    body = response.json()
    assert body["pool_id"] == str(second_pool_id)
    assert body["pool_name"] == "qualifying"
    assert len(body["rows"]) == 1
    assert body["rows"][0]["role"] == "miner"


def test_dashboard_analysis_requires_env_or_request_api_key(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router.settings.ANTHROPIC_API_KEY",
        None,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.post(f"/dashboard/v1/policies/versions/{uuid4()}/analysis")
    assert response.status_code == 500
    assert "Provide X-Anthropic-Api-Key" in response.json()["detail"]


def test_dashboard_analysis_accepts_request_scoped_api_key(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router.settings.ANTHROPIC_API_KEY",
        None,
    )

    async def fake_require_policy_version(_policy_version_id: str) -> tuple[Any, Any]:
        raise HTTPException(status_code=418, detail="request-key-path-reached")

    monkeypatch.setattr(
        "dashboard.backend.dashboard_backend.state_page.router._require_policy_version",
        fake_require_policy_version,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.post(
        f"/dashboard/v1/policies/versions/{uuid4()}/analysis",
        headers={"X-Anthropic-Api-Key": "sk-ant-test"},
    )
    assert response.status_code == 418
    assert response.json()["detail"] == "request-key-path-reached"
