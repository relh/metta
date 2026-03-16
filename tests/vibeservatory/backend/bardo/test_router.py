from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vibeservatory.backend.dashboard_backend.bardo.router as bardo_router
from metta.app_backend.models.job_request import JobStatus
from vibeservatory.backend.dashboard_backend.auth import User, get_softmax_user_or_raise
from vibeservatory.backend.dashboard_backend.bardo.router import BardoWorldStateResponse, create_bardo_router
from vibeservatory.backend.dashboard_backend.config import settings


@pytest.fixture(autouse=True)
def clear_bardo_world_state_cache() -> None:
    clear_cache = getattr(bardo_router, "_clear_bardo_world_state_cache", None)
    if clear_cache is not None:
        clear_cache()


def test_bardo_world_state_includes_active_jobs_for_softmax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_id = uuid4()
    policy_version_id = uuid4()
    active_job_id = uuid4()
    season_id = uuid4()

    policy = SimpleNamespace(
        id=policy_id,
        name="alpha-policy",
        user_id="user-alpha",
        versions=[
            SimpleNamespace(
                id=policy_version_id,
                version=3,
                created_at=datetime(2026, 3, 5, 1, 0, tzinfo=UTC),
            ),
        ],
    )
    job = SimpleNamespace(
        id=active_job_id,
        status=JobStatus.running,
        policy_versions=[SimpleNamespace(policy_version_id=policy_version_id)],
    )

    async def fake_fetch_all_policies(name_filter: str | None):
        assert name_filter == "alpha"
        return [policy]

    async def fake_fetch_active_episode_jobs(include_active_jobs: bool):
        assert include_active_jobs is True
        return [job]

    async def fake_resolve_user_names(user_ids: set[str]):
        assert user_ids == {"user-alpha"}
        return {"user-alpha": "Alice"}

    async def fake_fetch_canonical_seasons():
        return [
            SimpleNamespace(
                id=season_id,
                name="Beta CvC",
                version=7,
                compat_version="0.17",
                created_at=datetime(2026, 2, 26, 18, 36, tzinfo=UTC),
                pools=[SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())],
            )
        ]

    async def fake_fetch_pool_player_memberships_for_seasons(season_ids):
        assert season_ids == [season_id]
        return [(season_id, policy_version_id, False)]

    async def fake_get_softmax_user():
        return User(id="user-alpha", email="alice@softmax.com", is_softmax_team_member=True)

    monkeypatch.setattr(bardo_router, "_fetch_all_policies", fake_fetch_all_policies)
    monkeypatch.setattr(bardo_router, "_fetch_active_episode_jobs", fake_fetch_active_episode_jobs)
    monkeypatch.setattr(bardo_router, "_resolve_user_names", fake_resolve_user_names)
    monkeypatch.setattr(bardo_router, "_fetch_canonical_seasons", fake_fetch_canonical_seasons)
    monkeypatch.setattr(
        bardo_router,
        "_fetch_pool_player_memberships_for_seasons",
        fake_fetch_pool_player_memberships_for_seasons,
    )

    app = FastAPI()
    app.include_router(create_bardo_router())
    app.dependency_overrides[get_softmax_user_or_raise] = fake_get_softmax_user
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/bardo/v1/world-state?q=alpha")
    assert response.status_code == 200

    payload = response.json()
    assert payload["activeJobs"] == [
        {
            "id": str(active_job_id),
            "status": "running",
            "policyVersionIds": [str(policy_version_id)],
        }
    ]
    assert payload["totalPolicies"] == 1
    assert payload["policies"] == [
        {
            "policyId": str(policy_id),
            "policyVersionId": str(policy_version_id),
            "name": "alpha-policy",
            "userId": "user-alpha",
            "userName": "Alice",
            "createdAt": "2026-03-05T01:00:00Z",
            "activeJobIds": [str(active_job_id)],
            "seasonIds": [str(season_id)],
        }
    ]
    assert payload["seasons"] == [
        {
            "seasonId": str(season_id),
            "name": "Beta CvC",
            "version": 7,
            "compatVersion": "0.17",
            "createdAt": "2026-02-26T18:36:00Z",
            "stageCount": 2,
            "entrantCount": 1,
            "activeEntrantCount": 1,
        }
    ]
    assert isinstance(payload["generatedAt"], str)


def test_bardo_world_state_requires_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")

    app = FastAPI()
    app.include_router(create_bardo_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/bardo/v1/world-state")
    assert response.status_code == 401


def test_bardo_world_state_rejects_non_softmax_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "DASHBOARD_AUTH_SECRET", "test-secret")

    app = FastAPI()
    app.include_router(create_bardo_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get(
        "/bardo/v1/world-state",
        headers={
            "X-Auth-Secret": "test-secret",
            "X-User-Id": "user-beta",
            "X-User-Email": "beta@external.test",
            "X-User-Is-Softmax-Team-Member": "false",
        },
    )
    assert response.status_code == 403


def test_bardo_world_state_uses_etag_cache_and_304_for_matching_if_none_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_calls = 0

    async def fake_get_softmax_user():
        return User(id="user-alpha", email="alpha@softmax.com", is_softmax_team_member=True)

    async def fake_load_world_state(*, name_filter: str | None, include_active_jobs: bool) -> BardoWorldStateResponse:
        nonlocal load_calls
        load_calls += 1
        assert name_filter == "alpha"
        assert include_active_jobs is True
        return BardoWorldStateResponse(
            generatedAt="2026-03-07T18:36:00Z",
            totalPolicies=0,
            policies=[],
            activeJobs=[],
            seasons=[],
        )

    monkeypatch.setattr(bardo_router, "load_bardo_world_state", fake_load_world_state)
    monkeypatch.setattr(bardo_router, "WORLD_STATE_CACHE_TTL_SECONDS", 60.0)

    app = FastAPI()
    app.include_router(create_bardo_router())
    app.dependency_overrides[get_softmax_user_or_raise] = fake_get_softmax_user
    client = TestClient(app, base_url="http://localhost")

    first = client.get("/bardo/v1/world-state?q=alpha")
    assert first.status_code == 200
    assert first.headers.get("cache-control") == "private, no-cache"
    etag = first.headers.get("etag")
    assert etag is not None and etag
    assert load_calls == 1

    second = client.get("/bardo/v1/world-state?q=alpha", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers.get("etag") == etag
    assert second.headers.get("cache-control") == "private, no-cache"
    assert load_calls == 1


def test_bardo_world_state_limits_unfiltered_policy_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_policy_version_id = uuid4()
    active_job_id = uuid4()

    policies = [
        SimpleNamespace(
            id=uuid4(),
            name=f"policy-{idx:03d}",
            user_id=f"user-{idx:03d}",
            versions=[
                SimpleNamespace(
                    id=active_policy_version_id if idx == 54 else uuid4(),
                    version=1,
                    created_at=datetime(2026, 1, 1, 0, idx % 60, tzinfo=UTC),
                ),
            ],
        )
        for idx in range(55)
    ]
    active_job = SimpleNamespace(
        id=active_job_id,
        status=JobStatus.running,
        policy_versions=[SimpleNamespace(policy_version_id=active_policy_version_id)],
    )

    async def fake_fetch_all_policies(name_filter: str | None):
        assert name_filter is None
        return policies

    async def fake_fetch_active_episode_jobs(include_active_jobs: bool):
        assert include_active_jobs is True
        return [active_job]

    async def fake_resolve_user_names(user_ids: set[str]):
        return {user_id: user_id for user_id in user_ids}

    async def fake_fetch_canonical_seasons():
        return []

    async def fake_fetch_pool_player_memberships_for_seasons(season_ids):
        assert season_ids == []
        return []

    async def fake_get_softmax_user():
        return User(id="user-alpha", email="alpha@softmax.com", is_softmax_team_member=True)

    monkeypatch.setattr(bardo_router, "_fetch_all_policies", fake_fetch_all_policies)
    monkeypatch.setattr(bardo_router, "_fetch_active_episode_jobs", fake_fetch_active_episode_jobs)
    monkeypatch.setattr(bardo_router, "_resolve_user_names", fake_resolve_user_names)
    monkeypatch.setattr(bardo_router, "_fetch_canonical_seasons", fake_fetch_canonical_seasons)
    monkeypatch.setattr(
        bardo_router,
        "_fetch_pool_player_memberships_for_seasons",
        fake_fetch_pool_player_memberships_for_seasons,
    )

    app = FastAPI()
    app.include_router(create_bardo_router())
    app.dependency_overrides[get_softmax_user_or_raise] = fake_get_softmax_user
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/bardo/v1/world-state")
    assert response.status_code == 200

    payload = response.json()
    assert payload["totalPolicies"] == 55
    assert len(payload["policies"]) == 50
    assert str(active_policy_version_id) in {policy["policyVersionId"] for policy in payload["policies"]}


def test_bardo_world_state_keeps_all_active_policies_when_active_set_exceeds_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_jobs = []
    policies = []
    for idx in range(55):
        policy_version_id = uuid4()
        policies.append(
            SimpleNamespace(
                id=uuid4(),
                name=f"policy-{idx:03d}",
                user_id=f"user-{idx:03d}",
                versions=[
                    SimpleNamespace(
                        id=policy_version_id,
                        version=1,
                        created_at=datetime(2026, 1, 1, 0, idx % 60, tzinfo=UTC),
                    ),
                ],
            )
        )
        active_jobs.append(
            SimpleNamespace(
                id=uuid4(),
                status=JobStatus.running,
                policy_versions=[SimpleNamespace(policy_version_id=policy_version_id)],
            )
        )

    async def fake_fetch_all_policies(name_filter: str | None):
        assert name_filter is None
        return policies

    async def fake_fetch_active_episode_jobs(include_active_jobs: bool):
        assert include_active_jobs is True
        return active_jobs

    async def fake_resolve_user_names(user_ids: set[str]):
        return {user_id: user_id for user_id in user_ids}

    async def fake_fetch_canonical_seasons():
        return []

    async def fake_fetch_pool_player_memberships_for_seasons(season_ids):
        assert season_ids == []
        return []

    async def fake_get_softmax_user():
        return User(id="user-alpha", email="alpha@softmax.com", is_softmax_team_member=True)

    monkeypatch.setattr(bardo_router, "_fetch_all_policies", fake_fetch_all_policies)
    monkeypatch.setattr(bardo_router, "_fetch_active_episode_jobs", fake_fetch_active_episode_jobs)
    monkeypatch.setattr(bardo_router, "_resolve_user_names", fake_resolve_user_names)
    monkeypatch.setattr(bardo_router, "_fetch_canonical_seasons", fake_fetch_canonical_seasons)
    monkeypatch.setattr(
        bardo_router,
        "_fetch_pool_player_memberships_for_seasons",
        fake_fetch_pool_player_memberships_for_seasons,
    )

    app = FastAPI()
    app.include_router(create_bardo_router())
    app.dependency_overrides[get_softmax_user_or_raise] = fake_get_softmax_user
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/bardo/v1/world-state")
    assert response.status_code == 200

    payload = response.json()
    assert payload["totalPolicies"] == 55
    assert len(payload["policies"]) == 55
    returned_policy_ids = {policy["policyId"] for policy in payload["policies"]}
    assert returned_policy_ids == {str(policy.id) for policy in policies}
