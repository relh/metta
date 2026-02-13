import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from metta.app_backend.auth import User
from metta.app_backend.database import db_session
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.queries import episode_queries, policy_queries
from metta.app_backend.test_support.client_adapter import get_user_headers


@pytest.mark.asyncio
async def test_get_policy_versions_with_version_filter(
    test_client: TestClient, softmax_headers: dict[str, str]
) -> None:
    user = "version-filter@example.com"
    policy_id = await policy_queries.upsert_policy(name="version-filter-policy", user_id=user, attributes={})
    pv1_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )
    pv2_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    response = test_client.get(
        "/stats/policy-versions",
        params={"name_exact": "version-filter-policy", "version": 1},
        headers=softmax_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == str(pv1_id)
    assert body["entries"][0]["version"] == 1

    response = test_client.get(
        "/stats/policy-versions",
        params={"name_exact": "version-filter-policy", "version": 2},
        headers=softmax_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == str(pv2_id)
    assert body["entries"][0]["version"] == 2


@pytest.mark.asyncio
async def test_get_policies_with_filters(test_client: TestClient, softmax_headers: dict[str, str]) -> None:
    user = "policies-filter@example.com"
    await policy_queries.upsert_policy(name="alpha-policy", user_id=user, attributes={})
    await policy_queries.upsert_policy(name="beta-policy", user_id=user, attributes={})
    await policy_queries.upsert_policy(name="gamma-test", user_id=user, attributes={})

    # Use softmax user to bypass visibility filtering (testing query functionality, not visibility)
    response = test_client.get("/stats/policies", params={"name_exact": "alpha-policy"}, headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["entries"][0]["name"] == "alpha-policy"

    response = test_client.get("/stats/policies", params={"name_fuzzy": "policy"}, headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    names = {e["name"] for e in body["entries"]}
    assert names == {"alpha-policy", "beta-policy"}


@pytest.mark.asyncio
async def test_get_versions_for_policy(test_client: TestClient, softmax_headers: dict[str, str]) -> None:
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

    response = test_client.get("/stats/policy-versions", params={"policy_id": str(policy_id)}, headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 3
    assert len(body["entries"]) == 3
    versions = {e["version"] for e in body["entries"]}
    assert versions == {1, 2, 3}


@pytest.mark.asyncio
async def test_get_my_policy_versions(test_client: TestClient, softmax_headers: dict[str, str]) -> None:
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

    response = test_client.get("/stats/policy-versions", params={"mine": "true"}, headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == str(my_pv_id)
    assert body["entries"][0]["name"] == "my-policy"


@pytest.mark.asyncio
async def test_query_episodes_by_id_includes_avg_rewards_and_replay(
    test_client: TestClient, softmax_headers: dict[str, str]
) -> None:
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

    response = test_client.post(
        "/stats/episodes/query",
        json={"episode_ids": [str(episode_id)], "limit": 1},
        headers=softmax_headers,
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
# - Internal routes (policy creation, version creation, tags, bulk upload) require SoftmaxUser
# - Public routes (cogames CLI submit, read endpoints) use ExternalUser or are public


@pytest.mark.asyncio
async def test_update_policy_version_tags_requires_softmax(
    test_client: TestClient,
    regular_headers: dict[str, str],
    softmax_headers: dict[str, str],
) -> None:
    """Test that only softmax team members can update policy tags (internal route)."""
    owner_user = "owner@example.com"

    # Create a policy
    policy_id = await policy_queries.upsert_policy(name="owner-policy-tags", user_id=owner_user, attributes={})
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    # Non-softmax user should get 403
    response = test_client.put(
        f"/stats/policy-versions/{pv_id}/tags",
        json={"env": "prod"},
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax user can update tags on any policy (even not their own)
    response = test_client.put(
        f"/stats/policy-versions/{pv_id}/tags",
        json={"env": "prod"},
        headers=softmax_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_policy_version_requires_softmax(
    test_client: TestClient,
    regular_headers: dict[str, str],
    softmax_headers: dict[str, str],
) -> None:
    """Test that only softmax team members can create versions via internal route."""
    owner_user = "owner@example.com"

    # Create a policy
    policy_id = await policy_queries.upsert_policy(name="owner-policy-versions", user_id=owner_user, attributes={})

    # Non-softmax user should get 403
    response = test_client.post(
        f"/stats/policies/{policy_id}/versions",
        json={"policy_spec": {}, "attributes": {}},
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax user can create versions on any policy (even not their own)
    response = test_client.post(
        f"/stats/policies/{policy_id}/versions",
        json={"policy_spec": {}, "attributes": {}},
        headers=softmax_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_upsert_policy_requires_softmax(
    test_client: TestClient,
    regular_headers: dict[str, str],
    softmax_headers: dict[str, str],
) -> None:
    """Test that only softmax team members can use the internal policy creation route."""
    # Non-softmax user should get 403
    response = test_client.post(
        "/stats/policies",
        json={"name": "regular-user-policy", "is_system_policy": False},
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax team member can create policies
    response = test_client.post(
        "/stats/policies",
        json={"name": "softmax-policy", "is_system_policy": False},
        headers=softmax_headers,
    )
    assert response.status_code == 200

    # Softmax team member can create system policies
    response = test_client.post(
        "/stats/policies",
        json={"name": "system-policy", "is_system_policy": True},
        headers=softmax_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_policy_version_detail_internal_fields(
    test_client: TestClient,
    regular_headers: dict[str, str],
    softmax_headers: dict[str, str],
) -> None:
    """Test that internal fields are only populated for softmax users."""
    user = "owner@example.com"
    policy_id = await policy_queries.upsert_policy(name="detail-policy", user_id=user, attributes={})
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path="s3://bucket/path", git_hash="abc123", policy_spec={"key": "value"}, attributes={}
    )

    # Non-softmax user gets 200 but internal fields are null
    # Must be owned by the regular user so visibility filter passes
    regular_policy_id = await policy_queries.upsert_policy(
        name="regular-detail-policy", user_id="regular@example.com", attributes={}
    )
    regular_pv_id = await policy_queries.create_policy_version(
        policy_id=regular_policy_id,
        s3_path="s3://bucket/regular",
        git_hash="def456",
        policy_spec={"key": "val"},
        attributes={},
    )
    response = test_client.get(f"/stats/policy-versions/{regular_pv_id}", headers=regular_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["s3_path"] is None
    assert body["attributes"] == {}
    assert "git_hash" not in body
    assert "policy_spec" not in body

    # Softmax user sees internal fields
    response = test_client.get(f"/stats/policy-versions/{pv_id}", headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["s3_path"] == "s3://bucket/path"
    assert body["attributes"] == {}


@pytest.mark.asyncio
async def test_get_policy_version_detail_is_public(test_client: TestClient) -> None:
    """Test that policy version detail is accessible without auth for policies in public seasons."""
    user = "owner@example.com"
    policy_id = await policy_queries.upsert_policy(name="public-read-policy", user_id=user, attributes={})
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id, s3_path=None, git_hash=None, policy_spec={}, attributes={}
    )

    # Submit to a public season so anonymous users can see it
    async with db_session() as session:
        season = Season(name="beta-cvc", canonical=True)
        session.add(season)
        await session.flush()
        pool = Pool(season_id=season.id, name="public-pool")
        session.add(pool)
        await session.flush()
        pool_player = PoolPlayer(pool_id=pool.id, policy_version_id=pv_id)
        session.add(pool_player)
        await session.flush()

    # Request without auth headers should succeed for policies in public seasons
    response = test_client.get(f"/stats/policy-versions/{pv_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(pv_id)
    assert body["name"] == "public-read-policy"


@pytest.mark.asyncio
async def test_cogames_submit_routes_allow_regular_users(
    test_client: TestClient,
    regular_headers: dict[str, str],
) -> None:
    """Test that cogames submit routes are accessible to regular authenticated users."""
    # Regular users can get presigned URLs for policy submission
    response = test_client.post(
        "/stats/policies/submit/presigned-url",
        headers=regular_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "upload_url" in body
    assert "upload_id" in body


@pytest.mark.asyncio
async def test_bulk_upload_requires_softmax(
    test_client: TestClient,
    regular_headers: dict[str, str],
    softmax_headers: dict[str, str],
) -> None:
    """Test that bulk episode upload requires softmax team membership."""
    # Non-softmax user should get 403
    response = test_client.post(
        "/stats/episodes/bulk_upload/presigned-url",
        headers=regular_headers,
    )
    assert response.status_code == 403

    # Softmax user can access
    response = test_client.post(
        "/stats/episodes/bulk_upload/presigned-url",
        headers=softmax_headers,
    )
    assert response.status_code == 200


# --- Visibility Filtering Tests ---
# These tests verify that policies/policy versions are filtered based on:
# - Ownership (users can see their own policies)
# - Tournament season (policies submitted to non-hidden seasons are visible)
# - Softmax team membership (softmax users see everything)


async def _create_policy_with_season(
    session: AsyncSession, policy_name: str, user_id: str, season_name: str | None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper to create a policy with a version, optionally submitted to a season."""
    policy = Policy(name=policy_name, user_id=user_id)
    session.add(policy)
    await session.flush()

    pv = PolicyVersion(policy_id=policy.id, version=1)
    session.add(pv)
    await session.flush()

    if season_name is not None:
        # Check if season exists, otherwise create it

        season = (await session.execute(select(Season).filter_by(name=season_name))).scalar_one_or_none()
        if not season:
            season = Season(name=season_name, canonical=True)
            session.add(season)
            await session.flush()

        pool = Pool(season_id=season.id, name=f"{season_name}-pool")
        session.add(pool)
        await session.flush()

        pool_player = PoolPlayer(pool_id=pool.id, policy_version_id=pv.id)
        session.add(pool_player)
        await session.flush()

    return policy.id, pv.id


@pytest.mark.asyncio
async def test_visibility_policies_not_in_season_hidden_from_anonymous(test_client: TestClient) -> None:
    """Test that policies not submitted to any season are hidden from anonymous users."""
    async with db_session() as session:
        # Create a policy NOT submitted to any season
        policy_id, pv_id = await _create_policy_with_season(
            session, "unsubmitted-policy", "some-user@example.com", None
        )

    # Anonymous request should not see this policy
    response = test_client.get("/stats/policies")
    assert response.status_code == 200
    body = response.json()
    policy_ids = {e["id"] for e in body["entries"]}
    assert str(policy_id) not in policy_ids

    # Anonymous request should not see this policy version
    response = test_client.get("/stats/policy-versions")
    assert response.status_code == 200
    body = response.json()
    pv_ids = {e["id"] for e in body["entries"]}
    assert str(pv_id) not in pv_ids

    # Anonymous request should get 404 for this specific policy version
    response = test_client.get(f"/stats/policy-versions/{pv_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_visibility_policies_in_hidden_season_hidden_from_anonymous(test_client: TestClient) -> None:
    """Test that policies in hidden seasons (test-season, beta) are hidden from anonymous users."""
    async with db_session() as session:
        # Create a policy submitted to a hidden season ("test-season" is in HIDDEN_SEASONS)
        policy_id, pv_id = await _create_policy_with_season(
            session, "hidden-season-policy", "some-user@example.com", "test-season"
        )

    # Anonymous request should not see this policy
    response = test_client.get("/stats/policies")
    assert response.status_code == 200
    body = response.json()
    policy_ids = {e["id"] for e in body["entries"]}
    assert str(policy_id) not in policy_ids

    # Anonymous request should get 404 for this specific policy version
    response = test_client.get(f"/stats/policy-versions/{pv_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_visibility_policies_in_public_season_visible_to_anonymous(test_client: TestClient) -> None:
    """Test that policies in non-hidden seasons (e.g., beta-cvc) are visible to anonymous users."""
    async with db_session() as session:
        # Create a policy submitted to a non-hidden season ("beta-cvc" is not in HIDDEN_SEASONS)
        policy_id, pv_id = await _create_policy_with_season(
            session, "public-season-policy", "some-user@example.com", "beta-cvc"
        )

    # Anonymous request should see this policy
    response = test_client.get("/stats/policies")
    assert response.status_code == 200
    body = response.json()
    policy_ids = {e["id"] for e in body["entries"]}
    assert str(policy_id) in policy_ids

    # Anonymous request should see this policy version
    response = test_client.get("/stats/policy-versions")
    assert response.status_code == 200
    body = response.json()
    pv_ids = {e["id"] for e in body["entries"]}
    assert str(pv_id) in pv_ids

    # Anonymous request should be able to get this specific policy version
    response = test_client.get(f"/stats/policy-versions/{pv_id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(pv_id)


@pytest.mark.asyncio
async def test_visibility_owner_sees_own_policies_regardless_of_season(test_client: TestClient) -> None:
    """Test that policy owners can see their own policies regardless of tournament status."""
    owner_id = "owner@example.com"

    async with db_session() as session:
        # Create a policy NOT submitted to any season
        policy_id, pv_id = await _create_policy_with_season(session, "owner-unsubmitted-policy", owner_id, None)

    # Owner should see their own policy
    owner_headers = get_user_headers(User(id=owner_id, email=owner_id, is_softmax_team_member=False))
    response = test_client.get("/stats/policies", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    policy_ids = {e["id"] for e in body["entries"]}
    assert str(policy_id) in policy_ids

    # Owner should see their own policy version
    response = test_client.get("/stats/policy-versions", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    pv_ids = {e["id"] for e in body["entries"]}
    assert str(pv_id) in pv_ids

    # Owner should be able to get this specific policy version
    response = test_client.get(f"/stats/policy-versions/{pv_id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(pv_id)


@pytest.mark.asyncio
async def test_visibility_softmax_sees_all_policies(
    test_client: TestClient,
    softmax_headers: dict[str, str],
) -> None:
    """Test that softmax team members can see all policies regardless of ownership or season."""
    async with db_session() as session:
        # Create a policy NOT submitted to any season, owned by someone else
        policy_id, pv_id = await _create_policy_with_season(
            session, "softmax-visibility-policy", "random-user@example.com", None
        )

    # Softmax user should see the policy
    response = test_client.get("/stats/policies", headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    policy_ids = {e["id"] for e in body["entries"]}
    assert str(policy_id) in policy_ids

    # Softmax user should see the policy version
    response = test_client.get("/stats/policy-versions", headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    pv_ids = {e["id"] for e in body["entries"]}
    assert str(pv_id) in pv_ids

    # Softmax user should be able to get this specific policy version
    response = test_client.get(f"/stats/policy-versions/{pv_id}", headers=softmax_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(pv_id)


@pytest.mark.asyncio
async def test_visibility_versions_for_policy_filtered(
    test_client: TestClient,
    softmax_headers: dict[str, str],
) -> None:
    """Test that get_versions_for_policy respects visibility filtering."""

    async with db_session() as session:
        # Create a policy with two versions:
        # - Version 1: submitted to public season (visible)
        # - Version 2: not submitted (hidden from anonymous)
        policy = Policy(name="multi-version-visibility-policy", user_id="some-user@example.com")
        session.add(policy)
        await session.flush()

        pv1 = PolicyVersion(policy_id=policy.id, version=1)
        pv2 = PolicyVersion(policy_id=policy.id, version=2)
        session.add(pv1)
        session.add(pv2)
        await session.flush()

        # Submit version 1 to a public season
        season = Season(name="beta-cvc-versions-test", canonical=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="versions-test-pool")
        session.add(pool)
        await session.flush()

        pool_player = PoolPlayer(pool_id=pool.id, policy_version_id=pv1.id)
        session.add(pool_player)
        await session.flush()

        policy_id = policy.id
        pv1_id = pv1.id
        pv2_id = pv2.id

    # Anonymous request should only see version 1
    response = test_client.get("/stats/policy-versions", params={"policy_id": str(policy_id)})
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == str(pv1_id)

    # Softmax user should see both versions
    response = test_client.get("/stats/policy-versions", params={"policy_id": str(policy_id)}, headers=softmax_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    pv_ids = {e["id"] for e in body["entries"]}
    assert pv_ids == {str(pv1_id), str(pv2_id)}
