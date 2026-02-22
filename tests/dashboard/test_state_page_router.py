from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
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
