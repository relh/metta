from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vibeservatory.backend.dashboard_backend.bardo.router as bardo_router
from metta.app_backend.models.job_request import JobStatus
from vibeservatory.backend.dashboard_backend.auth import User, get_user
from vibeservatory.backend.dashboard_backend.bardo.router import create_bardo_router


def test_bardo_world_state_includes_active_jobs_for_softmax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_id = uuid4()
    policy_version_id = uuid4()
    active_job_id = uuid4()

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

    async def fake_get_user():
        return User(id="user-alpha", email="alice@softmax.com", is_softmax_team_member=True)

    monkeypatch.setattr(bardo_router, "_fetch_all_policies", fake_fetch_all_policies)
    monkeypatch.setattr(bardo_router, "_fetch_active_episode_jobs", fake_fetch_active_episode_jobs)
    monkeypatch.setattr(bardo_router, "_resolve_user_names", fake_resolve_user_names)

    app = FastAPI()
    app.include_router(create_bardo_router())
    app.dependency_overrides[get_user] = fake_get_user
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
    assert payload["policies"] == [
        {
            "policyId": str(policy_id),
            "policyVersionId": str(policy_version_id),
            "name": "alpha-policy",
            "userId": "user-alpha",
            "userName": "Alice",
            "createdAt": "2026-03-05T01:00:00Z",
            "activeJobIds": [str(active_job_id)],
        }
    ]
    assert isinstance(payload["generatedAt"], str)


def test_bardo_world_state_hides_active_jobs_for_non_softmax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_id = uuid4()
    policy_version_id = uuid4()

    policy = SimpleNamespace(
        id=policy_id,
        name="beta-policy",
        user_id="user-beta",
        versions=[
            SimpleNamespace(
                id=policy_version_id,
                version=1,
                created_at=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
            ),
        ],
    )

    async def fake_fetch_all_policies(name_filter: str | None):
        assert name_filter is None
        return [policy]

    async def fake_fetch_active_episode_jobs(include_active_jobs: bool):
        assert include_active_jobs is False
        return []

    async def fake_resolve_user_names(user_ids: set[str]):
        assert user_ids == {"user-beta"}
        return {}

    async def fake_get_user():
        return User(id="user-beta", email="beta@external.test", is_softmax_team_member=False)

    monkeypatch.setattr(bardo_router, "_fetch_all_policies", fake_fetch_all_policies)
    monkeypatch.setattr(bardo_router, "_fetch_active_episode_jobs", fake_fetch_active_episode_jobs)
    monkeypatch.setattr(bardo_router, "_resolve_user_names", fake_resolve_user_names)

    app = FastAPI()
    app.include_router(create_bardo_router())
    app.dependency_overrides[get_user] = fake_get_user
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/bardo/v1/world-state")
    assert response.status_code == 200

    payload = response.json()
    assert payload["activeJobs"] == []
    assert payload["policies"] == [
        {
            "policyId": str(policy_id),
            "policyVersionId": str(policy_version_id),
            "name": "beta-policy",
            "userId": "user-beta",
            "userName": "user-beta",
            "createdAt": "2026-03-04T18:00:00Z",
            "activeJobIds": [],
        }
    ]
