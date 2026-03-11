from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from vibeservatory.backend.dashboard_backend.state_page.router import (
    _agent_indices_from_tags,
    _default_winner_policy_version_id,
    create_dashboard_router,
)


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


def test_agent_indices_from_tags_falls_back_for_unparseable_assignments() -> None:
    tags = {
        "assignments": "3",
        "policy_version_ids": "['policy-a']",
    }

    assert _agent_indices_from_tags(tags, "policy-a", 6) == [0, 1, 2]


def test_agent_indices_from_tags_falls_back_for_non_indexable_policy_ids() -> None:
    tags = {
        "assignments": "[0, 1, 0, 1]",
        "policy_version_ids": "{'policy-a', 'policy-b'}",
    }

    assert _agent_indices_from_tags(tags, "policy-a", 6) == [0, 1, 2]


def test_default_dashboard_data_returns_404_when_default_policy_missing(monkeypatch: Any) -> None:
    async def fake_default_winner_policy_version_id(_session: Any) -> tuple[str | None, str | None]:
        return None, None

    @asynccontextmanager
    async def fake_db_session(*, read_only: bool = False) -> AsyncIterator[Any]:
        assert read_only
        yield SimpleNamespace()

    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._default_winner_policy_version_id",
        fake_default_winner_policy_version_id,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.db_session",
        fake_db_session,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/dashboard/v1/policies/versions/default/data")

    assert response.status_code == 404
    assert response.json()["detail"] == "No default policy version available"


def test_default_winner_policy_version_prefers_default_season_leader(monkeypatch: Any) -> None:
    default_season_id = uuid4()
    default_policy_id = uuid4()
    default_season = SimpleNamespace(
        id=default_season_id,
        name="beta-cvc",
        canonical=True,
        version=4,
    )
    calls: list[tuple[str, Any]] = []

    class _FakeCommissioner:
        async def get_leaderboard(self, pool_name: str | None = None) -> list[tuple[Any, float, int]]:
            calls.append(("get_leaderboard", pool_name))
            return [(default_policy_id, 1.23, 9)]

    async def fake_build_commissioner(season_name: str, *, season_id: Any) -> _FakeCommissioner:
        calls.append(("build_commissioner", (season_name, season_id)))
        return _FakeCommissioner()

    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.build_commissioner",
        fake_build_commissioner,
    )

    session = _FakeSession([_ExecuteResult(scalar=default_season)])
    winner_policy_id, winner_season_name = asyncio.run(_default_winner_policy_version_id(session))

    assert winner_policy_id == str(default_policy_id)
    assert winner_season_name == "beta-cvc"
    assert calls == [
        ("build_commissioner", ("beta-cvc", default_season_id)),
        ("get_leaderboard", None),
    ]


def test_default_winner_policy_version_falls_back_when_default_has_no_leader(monkeypatch: Any) -> None:
    default_season_id = uuid4()
    fallback_season_id = uuid4()
    fallback_policy_id = uuid4()
    default_season = SimpleNamespace(
        id=default_season_id,
        name="beta-cvc",
        canonical=True,
        version=4,
    )
    fallback_season = SimpleNamespace(
        id=fallback_season_id,
        name="beta-teams-small",
        canonical=True,
        version=6,
    )
    calls: list[tuple[str, Any]] = []

    class _FakeCommissioner:
        def __init__(self, leaderboard: list[tuple[Any, float, int]]) -> None:
            self._leaderboard = leaderboard

        async def get_leaderboard(self, pool_name: str | None = None) -> list[tuple[Any, float, int]]:
            calls.append(("get_leaderboard", pool_name))
            return self._leaderboard

    async def fake_build_commissioner(season_name: str, *, season_id: Any) -> _FakeCommissioner:
        calls.append(("build_commissioner", (season_name, season_id)))
        if season_name == "beta-cvc":
            return _FakeCommissioner([])
        assert season_name == "beta-teams-small"
        return _FakeCommissioner([(fallback_policy_id, 1.0, 10)])

    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.build_commissioner",
        fake_build_commissioner,
    )

    session = _FakeSession(
        [
            _ExecuteResult(scalar=default_season),
            _ExecuteResult(scalar_values=[fallback_season, default_season]),
        ]
    )
    winner_policy_id, winner_season_name = asyncio.run(_default_winner_policy_version_id(session))

    assert winner_policy_id == str(fallback_policy_id)
    assert winner_season_name == "beta-teams-small"
    assert calls == [
        ("build_commissioner", ("beta-cvc", default_season_id)),
        ("get_leaderboard", None),
        ("build_commissioner", ("beta-teams-small", fallback_season_id)),
        ("get_leaderboard", None),
    ]


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

    async def fake_fetch_sources(_policy_version_id: Any, _limit: int) -> tuple[list[Any], list[Any]]:
        return [], []

    async def fake_build_sorted_dashboard_episodes(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    calls: list[tuple[str, Any]] = []
    requested_policy_version_ids: list[str] = []

    async def fake_default_winner_policy_version_id(_session: Any) -> tuple[str | None, str | None]:
        return str(policy_version_id), "beta-teams-large"

    async def fake_require_policy_version(requested_policy_version_id: str) -> tuple[Any, Any]:
        requested_policy_version_ids.append(requested_policy_version_id)
        return policy_version_id, fake_policy_version

    class _FakeCommissioner:
        async def get_leaderboard(self, pool_name: str | None = None) -> list[tuple[Any, float, int]]:
            calls.append(("get_leaderboard", pool_name))
            return [(policy_version_id, 1.23, 9)]

    async def fake_build_commissioner(season_name: str, *, season_id: Any) -> _FakeCommissioner:
        calls.append((season_name, season_id))
        return _FakeCommissioner()

    @asynccontextmanager
    async def fake_db_session(*, read_only: bool = False) -> AsyncIterator[Any]:
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
        "vibeservatory.backend.dashboard_backend.state_page.router._require_policy_version",
        fake_require_policy_version,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._default_winner_policy_version_id",
        fake_default_winner_policy_version_id,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._fetch_policy_dashboard_sources",
        fake_fetch_sources,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._build_sorted_dashboard_episodes",
        fake_build_sorted_dashboard_episodes,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.build_commissioner",
        fake_build_commissioner,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.db_session",
        fake_db_session,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get(f"/dashboard/v1/policies/versions/{policy_version_id}/data")
    default_response = client.get("/dashboard/v1/policies/versions/default/data")

    assert response.status_code == 200
    assert default_response.status_code == 200
    assert requested_policy_version_ids == [str(policy_version_id), str(policy_version_id)]
    assert calls[0] == ("beta-teams-large", season_id)
    assert calls[1] == ("get_leaderboard", None)
    assert calls[2] == ("beta-teams-large", season_id)
    assert calls[3] == ("get_leaderboard", None)
    payload = response.json()
    derived = payload["derived"]
    assert "unsupported" in derived
    assert "instrumentation" in derived
    assert "stats_inventory" in derived
    assert "actions" in derived
    assert "orchestration" in derived


def test_dashboard_data_embeds_role_percentiles_when_requested(monkeypatch: Any) -> None:
    policy_version_id = uuid4()
    policy_id = uuid4()

    fake_policy_version = SimpleNamespace(
        id=policy_version_id,
        version=3,
        policy_id=policy_id,
        policy=SimpleNamespace(name="gimpy"),
    )

    async def fake_require_policy_version(_policy_version_id: str) -> tuple[Any, Any]:
        return policy_version_id, fake_policy_version

    async def fake_fetch_sources(_policy_version_id: Any, _limit: int) -> tuple[list[Any], list[Any]]:
        return [], []

    async def fake_build_sorted_dashboard_episodes(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    include_calls: list[Any] = []

    async def fake_build_role_percentiles_response(pv_id: Any) -> dict[str, Any]:
        include_calls.append(pv_id)
        return {
            "pool_id": "pool-1",
            "pool_name": "leaderboard",
            "roles": {},
            "rows": [],
        }

    def fake_build_diagnose_run_summaries() -> list[dict[str, Any]]:
        return [
            {
                "run_id": "run-1",
                "manifest": {"run_id": "run-1", "created_at": "2026-02-25T00:00:00Z"},
            }
        ]

    @asynccontextmanager
    async def fake_db_session(*, read_only: bool = False) -> AsyncIterator[Any]:
        assert read_only
        session = _FakeSession(
            [
                _ExecuteResult(scalar=None),
                _ExecuteResult(scalar=None),
                _ExecuteResult(scalar_values=[]),
            ]
        )
        yield session

    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._require_policy_version",
        fake_require_policy_version,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._fetch_policy_dashboard_sources",
        fake_fetch_sources,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._build_sorted_dashboard_episodes",
        fake_build_sorted_dashboard_episodes,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._build_role_percentiles_response",
        fake_build_role_percentiles_response,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._build_diagnose_run_summaries",
        fake_build_diagnose_run_summaries,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.db_session",
        fake_db_session,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get(
        f"/dashboard/v1/policies/versions/{policy_version_id}/data?include=role_percentiles,diagnose_runs"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["role_percentiles"]["pool_id"] == "pool-1"
    assert payload["diagnose_runs"][0]["run_id"] == "run-1"
    assert include_calls == [policy_version_id]

    response_without_include = client.get(f"/dashboard/v1/policies/versions/{policy_version_id}/data")
    assert response_without_include.status_code == 200
    payload_without_include = response_without_include.json()
    assert payload_without_include["role_percentiles"] is None
    assert payload_without_include["diagnose_runs"] is None
    assert include_calls == [policy_version_id]


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
    async def fake_db_session(*, read_only: bool = False) -> AsyncIterator[Any]:
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
        "vibeservatory.backend.dashboard_backend.state_page.router._require_policy_version",
        fake_require_policy_version,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.db_session",
        fake_db_session,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._candidate_role_pools_for_policy",
        fake_candidate_role_pools_for_policy,
    )
    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router.compute_policy_role_percentiles",
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


def test_dashboard_analysis_uses_bedrock_without_request_key(monkeypatch: Any) -> None:
    """Without X-Anthropic-Api-Key header, the endpoint proceeds to Bedrock (no 500)."""

    async def fake_require_policy_version(_policy_version_id: str) -> tuple[Any, Any]:
        raise HTTPException(status_code=418, detail="bedrock-path-reached")

    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._require_policy_version",
        fake_require_policy_version,
    )

    app = FastAPI()
    app.include_router(create_dashboard_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.post(f"/dashboard/v1/policies/versions/{uuid4()}/analysis")
    assert response.status_code == 418
    assert response.json()["detail"] == "bedrock-path-reached"


def test_dashboard_analysis_accepts_request_scoped_api_key(monkeypatch: Any) -> None:
    async def fake_require_policy_version(_policy_version_id: str) -> tuple[Any, Any]:
        raise HTTPException(status_code=418, detail="request-key-path-reached")

    monkeypatch.setattr(
        "vibeservatory.backend.dashboard_backend.state_page.router._require_policy_version",
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
