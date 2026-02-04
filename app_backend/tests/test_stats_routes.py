import uuid

import pytest
from fastapi.testclient import TestClient

from metta.app_backend.auth import User
from metta.app_backend.queries import episode_queries, policy_queries
from metta.app_backend.test_support.client_adapter import get_user_headers


@pytest.mark.asyncio
async def test_get_policy_versions_with_version_filter(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    user = "version-filter@example.com"
    policy_id = await policy_queries.upsert_policy(name="version-filter-policy", user_id=user, attributes={})
    pv1_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )
    pv2_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    response = isolated_test_client.get(
        "/stats/policy-versions",
        params={"name_exact": "version-filter-policy", "version": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == str(pv1_id)
    assert body["entries"][0]["version"] == 1

    response = isolated_test_client.get(
        "/stats/policy-versions",
        params={"name_exact": "version-filter-policy", "version": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == str(pv2_id)
    assert body["entries"][0]["version"] == 2


@pytest.mark.asyncio
async def test_get_policies_with_filters(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    user = "policies-filter@example.com"
    await policy_queries.upsert_policy(name="alpha-policy", user_id=user, attributes={})
    await policy_queries.upsert_policy(name="beta-policy", user_id=user, attributes={})
    await policy_queries.upsert_policy(name="gamma-test", user_id=user, attributes={})

    response = isolated_test_client.get("/stats/policies", params={"name_exact": "alpha-policy"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["entries"][0]["name"] == "alpha-policy"

    response = isolated_test_client.get("/stats/policies", params={"name_fuzzy": "policy"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    names = {e["name"] for e in body["entries"]}
    assert names == {"alpha-policy", "beta-policy"}


@pytest.mark.asyncio
async def test_get_versions_for_policy(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    user = "versions-for-policy@example.com"
    policy_id = await policy_queries.upsert_policy(name="multi-version-policy", user_id=user, attributes={})
    await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )
    await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )
    await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    response = isolated_test_client.get(f"/stats/policies/{policy_id}/versions")
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 3
    assert len(body["entries"]) == 3
    versions = {e["version"] for e in body["entries"]}
    assert versions == {1, 2, 3}


@pytest.mark.asyncio
async def test_get_my_policy_versions(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    my_user = "debug_user_id"
    other_user = "other@example.com"

    my_policy_id = await policy_queries.upsert_policy(name="my-policy", user_id=my_user, attributes={})
    my_pv_id = await policy_queries.create_policy_version(
        policy_id=my_policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    other_policy_id = await policy_queries.upsert_policy(name="other-policy", user_id=other_user, attributes={})
    await policy_queries.create_policy_version(
        policy_id=other_policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    response = isolated_test_client.get("/stats/policies/my-versions", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == str(my_pv_id)
    assert body["entries"][0]["name"] == "my-policy"


@pytest.mark.asyncio
async def test_query_episodes_by_id_includes_avg_rewards_and_replay(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    _ = isolated_stats_repo  # needed to configure database globals
    user = "episodes@example.com"
    policy_id = await policy_queries.upsert_policy(name="episodes-policy", user_id=user, attributes={})
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id,
        s3_path=None,
        git_hash=None,
        policy_spec={},
        attributes={},
    )

    episode_id = uuid.uuid4()
    await episode_queries.record_episode(
        id=episode_id,
        data_uri=f"s3://episodes/{uuid.uuid4()}",
        replay_url="https://example.com/replays/episode-test",
        attributes={"note": "avg reward should be computed"},
        eval_task_id=None,
        thumbnail_url=None,
        tags=[("sim_name", "arena-basic")],
        policy_versions=[(pv_id, 2)],
        policy_metrics=[(pv_id, "reward", 10.0)],
    )

    response = isolated_test_client.post(
        "/stats/episodes/query",
        json={"episode_ids": [str(episode_id)], "limit": 1},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert "episodes" in body
    episodes = body["episodes"]
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["id"] == str(episode_id)
    assert episode["replay_url"] == "https://example.com/replays/episode-test"
    assert episode["avg_rewards"][str(pv_id)] == pytest.approx(5.0)


# --- Authorization Tests ---
# These tests verify the auth model:
# - Internal routes (policy creation, version creation, tags, bulk upload) require CheckSoftmaxUser
# - Public routes (cogames CLI submit, read endpoints) use CheckUser or are public


def _get_headers_for_user(user_id: str, is_softmax: bool = False) -> dict[str, str]:
    """Create auth headers for a test user."""
    user = User(id=user_id, email=f"{user_id}@example.com", is_softmax_team_member=is_softmax)
    return get_user_headers(user)


@pytest.mark.asyncio
async def test_update_policy_version_tags_requires_softmax(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    """Test that only softmax team members can update policy tags (internal route)."""
    owner_user = "owner@example.com"

    # Create a policy
    policy_id = await policy_queries.upsert_policy(name="owner-policy-tags", user_id=owner_user, attributes={})
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    # Non-softmax user should get 403
    regular_headers = _get_headers_for_user("regular@example.com", is_softmax=False)
    response = isolated_test_client.put(
        f"/stats/policies/versions/{pv_id}/tags",
        json={"env": "prod"},
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax user can update tags on any policy (even not their own)
    softmax_headers = _get_headers_for_user("team@softmax.com", is_softmax=True)
    response = isolated_test_client.put(
        f"/stats/policies/versions/{pv_id}/tags",
        json={"env": "prod"},
        headers=softmax_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_policy_version_requires_softmax(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    """Test that only softmax team members can create versions via internal route."""
    owner_user = "owner@example.com"

    # Create a policy
    policy_id = await policy_queries.upsert_policy(name="owner-policy-versions", user_id=owner_user, attributes={})

    # Non-softmax user should get 403
    regular_headers = _get_headers_for_user("regular@example.com", is_softmax=False)
    response = isolated_test_client.post(
        f"/stats/policies/{policy_id}/versions",
        json={"policy_spec": {}, "attributes": {}},
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax user can create versions on any policy (even not their own)
    softmax_headers = _get_headers_for_user("team@softmax.com", is_softmax=True)
    response = isolated_test_client.post(
        f"/stats/policies/{policy_id}/versions",
        json={"policy_spec": {}, "attributes": {}},
        headers=softmax_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_upsert_policy_requires_softmax(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    """Test that only softmax team members can use the internal policy creation route."""
    # Non-softmax user should get 403
    regular_headers = _get_headers_for_user("regular@example.com", is_softmax=False)
    response = isolated_test_client.post(
        "/stats/policies",
        json={"name": "regular-user-policy", "is_system_policy": False},
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax team member can create policies
    softmax_headers = _get_headers_for_user("team@softmax.com", is_softmax=True)
    response = isolated_test_client.post(
        "/stats/policies",
        json={"name": "softmax-policy", "is_system_policy": False},
        headers=softmax_headers,
    )
    assert response.status_code == 200

    # Softmax team member can create system policies
    response = isolated_test_client.post(
        "/stats/policies",
        json={"name": "system-policy", "is_system_policy": True},
        headers=softmax_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_policy_version_with_details_requires_softmax(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    """Test that getting policy version with internal details requires softmax."""
    user = "owner@example.com"
    policy_id = await policy_queries.upsert_policy(name="detail-policy", user_id=user, attributes={})
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path="s3://bucket/path", git_hash="abc123", policy_spec={"key": "value"}, attributes={}
    )

    # Non-softmax user should get 403
    regular_headers = _get_headers_for_user("regular@example.com", is_softmax=False)
    response = isolated_test_client.get(
        f"/stats/policies/versions/{pv_id}",
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax user can access
    softmax_headers = _get_headers_for_user("team@softmax.com", is_softmax=True)
    response = isolated_test_client.get(
        f"/stats/policies/versions/{pv_id}",
        headers=softmax_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["s3_path"] == "s3://bucket/path"
    assert body["git_hash"] == "abc123"
    assert body["policy_spec"] == {"key": "value"}


@pytest.mark.asyncio
async def test_get_policy_by_id_is_public(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    """Test that get_policy_by_id is public and doesn't require auth."""
    user = "owner@example.com"
    policy_id = await policy_queries.upsert_policy(name="public-read-policy", user_id=user, attributes={})
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    # Request without auth headers should succeed
    response = isolated_test_client.get(f"/stats/policies/{pv_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(pv_id)
    assert body["name"] == "public-read-policy"


@pytest.mark.asyncio
async def test_cogames_submit_routes_allow_regular_users(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    """Test that cogames submit routes are accessible to regular authenticated users."""
    regular_headers = _get_headers_for_user("regular@example.com", is_softmax=False)

    # Regular users can get presigned URLs for policy submission
    response = isolated_test_client.post(
        "/stats/policies/submit/presigned-url",
        headers=regular_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "upload_url" in body
    assert "upload_id" in body


@pytest.mark.asyncio
async def test_bulk_upload_requires_softmax(
    isolated_stats_repo: str,  # noqa: ARG001
    isolated_test_client: TestClient,
) -> None:
    """Test that bulk episode upload requires softmax team membership."""
    # Non-softmax user should get 403
    regular_headers = _get_headers_for_user("regular@example.com", is_softmax=False)
    response = isolated_test_client.post(
        "/stats/episodes/bulk_upload/presigned-url",
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax user can access
    softmax_headers = _get_headers_for_user("team@softmax.com", is_softmax=True)
    response = isolated_test_client.post(
        "/stats/episodes/bulk_upload/presigned-url",
        headers=softmax_headers,
    )
    assert response.status_code == 200
