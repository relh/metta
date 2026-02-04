import uuid

import pytest
from fastapi.testclient import TestClient

from metta.app_backend.queries import episode_queries, policy_queries


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
