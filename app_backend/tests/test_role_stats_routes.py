import uuid
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from metta.app_backend.database import db_session
from metta.app_backend.models.job_request import JobRequest, JobType
from metta.app_backend.models.tournament import Match, MatchStatus, Pool, Season
from metta.app_backend.queries import episode_queries, policy_queries, role_percentile_queries

DEFAULT_AGENT_METRICS = [
    (0, "miner.gained", 10.0),
    (1, "miner.gained", 10.0),
    (0, "junction.aligned_by_agent", 4.0),
    (1, "junction.aligned_by_agent", 4.0),
    (2, "miner.gained", 1.0),
    (3, "miner.gained", 1.0),
    (2, "junction.aligned_by_agent", 1.0),
    (3, "junction.aligned_by_agent", 1.0),
]


async def _create_policy_versions(name_prefix: str) -> tuple[UUID, UUID]:
    policy_id = await policy_queries.upsert_policy(
        name=f"{name_prefix}-{uuid.uuid4().hex[:6]}",
        user_id="u",
        attributes={},
    )
    pv1_id = await policy_queries.create_policy_version(
        policy_id=policy_id,
        s3_path=None,
        git_hash=None,
        policy_spec={},
        attributes={},
    )
    pv2_id = await policy_queries.create_policy_version(
        policy_id=policy_id,
        s3_path=None,
        git_hash=None,
        policy_spec={},
        attributes={},
    )
    return pv1_id, pv2_id


async def _create_pool_with_completed_match(name_prefix: str) -> tuple[UUID, UUID]:
    async with db_session() as session:
        season = Season(name=f"{name_prefix}-{uuid.uuid4().hex[:6]}", version=1, canonical=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="competition")
        session.add(pool)

        job = JobRequest(job_type=JobType.episode, job={}, user_id="u")
        session.add(job)
        await session.flush()

        session.add(
            Match(
                pool_id=pool.id,
                job_id=job.id,
                assignments=[0, 0, 1, 1],
                status=MatchStatus.completed,
            )
        )
        await session.flush()

        return pool.id, job.id


async def _create_pool_without_match(name_prefix: str) -> UUID:
    async with db_session() as session:
        season = Season(name=f"{name_prefix}-{uuid.uuid4().hex[:6]}", version=1, canonical=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="competition")
        session.add(pool)
        await session.flush()

        return pool.id


async def _record_episode_for_pool(
    job_id: UUID,
    pv1_id: UUID,
    pv2_id: UUID,
    agent_metrics: list[tuple[int, str, float]],
) -> None:
    episode_id = uuid.uuid4()
    await episode_queries.record_episode(
        id=episode_id,
        data_uri=f"s3://episodes/{uuid.uuid4()}",
        replay_url=None,
        attributes={},
        eval_task_id=None,
        thumbnail_url=None,
        tags=[],
        policy_versions=[(pv1_id, 2), (pv2_id, 2)],
        policy_metrics=[],
        agent_policies={0: pv1_id, 1: pv1_id, 2: pv2_id, 3: pv2_id},
        agent_metrics=agent_metrics,
    )
    await episode_queries.link_episode_job(episode_id, job_id)


def _role_row(rows: list[dict[str, Any]], role: str) -> dict[str, Any]:
    return next(row for row in rows if row["role"] == role)


@pytest.mark.asyncio
async def test_role_percentiles_get(test_client: TestClient) -> None:
    pv1_id, pv2_id = await _create_policy_versions("role-stats")
    pool_id, job_id = await _create_pool_with_completed_match("role-stats")
    await _record_episode_for_pool(job_id, pv1_id, pv2_id, DEFAULT_AGENT_METRICS)

    rows1 = test_client.get(f"/stats/roles/pools/{pool_id}/policy-versions/{pv1_id}").json()
    miner_row1 = _role_row(rows1, "miner")
    assert miner_row1["percentile"] == pytest.approx(100.0)
    assert miner_row1["details"]["metrics"]["miner.gained"]["avg"] == pytest.approx(10.0)

    rows2 = test_client.get(f"/stats/roles/pools/{pool_id}/policy-versions/{pv2_id}").json()
    miner_row2 = _role_row(rows2, "miner")
    assert miner_row2["percentile"] == pytest.approx(0.0)
    assert miner_row2["details"]["metrics"]["miner.gained"]["avg"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_role_leaderboard_get(test_client: TestClient) -> None:
    pv1_id, pv2_id = await _create_policy_versions("role-stats")
    pool_id, job_id = await _create_pool_with_completed_match("role-stats")
    await _record_episode_for_pool(job_id, pv1_id, pv2_id, DEFAULT_AGENT_METRICS)

    leaderboard = test_client.get(f"/stats/roles/pools/{pool_id}/roles/miner/leaderboard")
    assert leaderboard.status_code == 200
    entries = leaderboard.json()
    assert entries[0]["rank"] == 1
    assert entries[0]["policy_version_id"] == str(pv1_id)
    assert entries[1]["rank"] == 2
    assert entries[1]["policy_version_id"] == str(pv2_id)


@pytest.mark.asyncio
async def test_role_percentiles_404_when_pool_has_no_role_metrics(test_client: TestClient) -> None:
    policy_id = await policy_queries.upsert_policy(
        name=f"role-stats-{uuid.uuid4().hex[:6]}",
        user_id="u",
        attributes={},
    )
    pv_id = await policy_queries.create_policy_version(
        policy_id=policy_id,
        s3_path=None,
        git_hash=None,
        policy_spec={},
        attributes={},
    )
    pool_id = await _create_pool_without_match("role-stats")

    response = test_client.get(f"/stats/roles/pools/{pool_id}/policy-versions/{pv_id}")
    assert response.status_code == 404


def test_role_definitions_include_deaths(test_client: TestClient) -> None:
    response = test_client.get("/stats/roles/definitions")
    assert response.status_code == 200
    body = response.json()
    for role in ("miner", "scout", "scrambler", "aligner"):
        role_metrics = body["roles"][role]
        deaths = next((metric for metric in role_metrics if metric["key"] == "deaths"), None)
        assert deaths is not None
        assert len(deaths["source_names"]) > 0


def test_role_definitions_use_single_canonical_source_names(test_client: TestClient) -> None:
    response = test_client.get("/stats/roles/definitions")
    assert response.status_code == 200
    body = response.json()
    for role in ("miner", "scout", "scrambler", "aligner"):
        role_metrics = body["roles"][role]
        for metric in role_metrics:
            assert len(metric["source_names"]) == 1


@pytest.mark.asyncio
async def test_missing_metric_samples_are_excluded_from_percentiles(test_client: TestClient) -> None:
    pv1_id, pv2_id = await _create_policy_versions("role-missing-metric")
    pool_id, job_id = await _create_pool_with_completed_match("role-missing-metric")
    await _record_episode_for_pool(
        job_id,
        pv1_id,
        pv2_id,
        [
            (0, "miner.gained", 5.0),
            (1, "miner.gained", 5.0),
            (2, "miner.gained", 1.0),
            (3, "miner.gained", 1.0),
            (0, "deaths", 3.0),
            (1, "deaths", 3.0),
        ],
    )

    rows1 = test_client.get(f"/stats/roles/pools/{pool_id}/policy-versions/{pv1_id}").json()
    rows2 = test_client.get(f"/stats/roles/pools/{pool_id}/policy-versions/{pv2_id}").json()
    miner_row1 = _role_row(rows1, "miner")
    miner_row2 = _role_row(rows2, "miner")

    assert miner_row1["percentile"] == pytest.approx(100.0)
    assert miner_row2["percentile"] == pytest.approx(0.0)

    assert miner_row1["details"]["metrics"]["deaths"]["samples"] == 2
    assert "deaths" not in miner_row2["details"]["metrics"]


@pytest.mark.asyncio
async def test_role_leaderboard_computes_only_requested_role(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pv1_id, pv2_id = await _create_policy_versions("role-leaderboard-scope")
    pool_id, job_id = await _create_pool_with_completed_match("role-leaderboard-scope")
    await _record_episode_for_pool(job_id, pv1_id, pv2_id, DEFAULT_AGENT_METRICS)

    called_metric_keys: list[str] = []
    expected_metric_keys = {metric.key for metric in role_percentile_queries.ROLE_METRICS["miner"]}
    original_metric_percentiles = role_percentile_queries._metric_percentiles

    async def _record_metric_calls(pool_id: UUID, metric: role_percentile_queries.RoleMetric) -> list[dict[str, Any]]:
        called_metric_keys.append(metric.key)
        return await original_metric_percentiles(pool_id, metric)

    monkeypatch.setattr(role_percentile_queries, "_metric_percentiles", _record_metric_calls)

    response = test_client.get(f"/stats/roles/pools/{pool_id}/roles/miner/leaderboard")
    assert response.status_code == 200
    assert called_metric_keys
    assert set(called_metric_keys).issubset(expected_metric_keys)
