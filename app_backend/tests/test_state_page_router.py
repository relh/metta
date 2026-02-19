import typing
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from fastapi.routing import APIRoute

import metta.app_backend.state_page.episode_builder as episode_builder
import metta.app_backend.state_page.router as state_page_router
from metta.app_backend.auth import get_softmax_user_or_raise
from metta.app_backend.models.job_request import JobStatus
from metta.app_backend.server import create_app
from metta.app_backend.state_page.diagnostics import (
    DashboardEpisode,
    FailureSummary,
    OutcomeSnapshot,
    OutcomeSummary,
    compute_action_summary,
    compute_failure_summary,
    compute_opponent_metrics,
)


@pytest.mark.asyncio
async def test_build_dashboard_episodes_includes_failed_jobs_for_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_version_id = uuid4()
    opponent_id = uuid4()
    completed_job_id = uuid4()
    failed_with_episode_job_id = uuid4()
    failed_without_episode_job_id = uuid4()

    async def _mock_get_policy_version_with_name(_policy_version_id: object) -> None:
        return None

    monkeypatch.setattr(
        episode_builder.policy_queries,
        "get_policy_version_with_name",
        _mock_get_policy_version_with_name,
    )

    raw_episodes = [
        SimpleNamespace(
            id=uuid4(),
            job_id=completed_job_id,
            avg_rewards={policy_version_id: 1.2, opponent_id: 0.8},
            tags={
                "assignments": "[0, 1]",
                "policy_version_ids": f"['{policy_version_id}', '{opponent_id}']",
            },
            attributes={"steps": 128, "stats": {"agent": [{"action.move.success": 7}, {}]}},
            created_at=datetime(2026, 2, 13, 10, 0, 0),
            replay_url="s3://replay/completed",
            thumbnail_url="s3://thumb/completed",
        ),
        SimpleNamespace(
            id=uuid4(),
            job_id=failed_with_episode_job_id,
            avg_rewards={policy_version_id: 0.0, opponent_id: 1.0},
            tags={
                "assignments": "[0, 1]",
                "policy_version_ids": f"['{policy_version_id}', '{opponent_id}']",
            },
            attributes={"steps": 0, "stats": {"agent": [{}, {}]}},
            created_at=datetime(2026, 2, 13, 10, 5, 0),
            replay_url=None,
            thumbnail_url=None,
        ),
    ]
    policy_jobs = [
        SimpleNamespace(
            id=completed_job_id,
            status=JobStatus.completed,
            error_type=None,
            error=None,
            result=None,
            created_at=datetime(2026, 2, 13, 10, 0, 0),
        ),
        SimpleNamespace(
            id=failed_with_episode_job_id,
            status=JobStatus.failed,
            error_type="timeout",
            error="timed out",
            result={"stderr": "timeout"},
            created_at=datetime(2026, 2, 13, 10, 5, 0),
        ),
        SimpleNamespace(
            id=failed_without_episode_job_id,
            status=JobStatus.failed,
            error_type="oom_killed",
            error="OOMKilled",
            result={"message": "OOMKilled"},
            created_at=datetime(2026, 2, 13, 10, 6, 0),
        ),
    ]

    episodes = await episode_builder.build_dashboard_episodes(
        raw_episodes=raw_episodes,
        policy_version_id=policy_version_id,
        policy_version_id_str=str(policy_version_id),
        policy_jobs=policy_jobs,
        opponent_cache={},
    )

    assert len(episodes) == 3

    by_job_id = {episode.job_id: episode for episode in episodes}
    assert by_job_id[str(completed_job_id)].status == "completed"
    assert by_job_id[str(failed_with_episode_job_id)].status == "failed"
    assert by_job_id[str(failed_without_episode_job_id)].status == "failed"
    assert by_job_id[str(failed_without_episode_job_id)].episode_id == f"failed-job-{failed_without_episode_job_id}"


@pytest.mark.asyncio
async def test_build_dashboard_episodes_deduplicates_duplicate_failed_job_rows() -> None:
    policy_version_id = uuid4()
    duplicate_failed_job_id = uuid4()
    duplicate_failed_job = SimpleNamespace(
        id=duplicate_failed_job_id,
        status=JobStatus.failed,
        error_type="timeout",
        error="timed out",
        result={"stderr": "timeout"},
        created_at=datetime(2026, 2, 13, 10, 5, 0),
    )

    episodes = await episode_builder.build_dashboard_episodes(
        raw_episodes=[],
        policy_version_id=policy_version_id,
        policy_version_id_str=str(policy_version_id),
        policy_jobs=[duplicate_failed_job, duplicate_failed_job],
        opponent_cache={},
    )

    assert len(episodes) == 1
    assert episodes[0].job_id == str(duplicate_failed_job_id)
    assert episodes[0].episode_id == f"failed-job-{duplicate_failed_job_id}"


def test_compute_failure_summary_counts_error_buckets_and_health_signals() -> None:
    episodes = [
        DashboardEpisode(
            episode_id="ep-timeout",
            job_id="job-timeout",
            opponent_name="opp",
            opponent_version=1,
            team_composition="4v4",
            reward=0.0,
            status="failed",
            error_type="timeout",
            steps=0,
            metrics={},
        ),
        DashboardEpisode(
            episode_id="ep-oom",
            job_id="job-oom",
            opponent_name="opp",
            opponent_version=1,
            team_composition="4v4",
            reward=0.0,
            status="failed",
            error_type="oom_killed",
            steps=0,
            metrics={},
        ),
        DashboardEpisode(
            episode_id="ep-crash",
            job_id="job-crash",
            opponent_name="opp",
            opponent_version=1,
            team_composition="4v4",
            reward=0.0,
            status="failed",
            error_type="policy_error",
            steps=0,
            metrics={},
        ),
        DashboardEpisode(
            episode_id="ep-other",
            job_id="job-other",
            opponent_name="opp",
            opponent_version=1,
            team_composition="4v4",
            reward=0.0,
            status="failed",
            error_type="node_preempted",
            steps=0,
            metrics={},
        ),
        DashboardEpisode(
            episode_id="ep-freeze",
            job_id="job-freeze",
            opponent_name="opp",
            opponent_version=1,
            team_composition="4v4",
            reward=1.0,
            status="completed",
            steps=100,
            metrics={
                "status.frozen.ticks": 25,
                "action.noop.success": 50,
                "action.move.success": 10,
                "action.failed": 5,
            },
        ),
    ]

    summary = compute_failure_summary(episodes)

    assert summary.timeout_failures == 1
    assert summary.oom_failures == 1
    assert summary.crash_failures == 1
    assert summary.other_failures == 1
    assert summary.freeze_heavy_completed == 1
    assert summary.noop_heavy_completed == 1


def test_compute_action_summary_blocks_on_reliability_regressions() -> None:
    outcome = OutcomeSummary(
        verdict="helped",
        reason="",
        evidence_sufficient=True,
        current=OutcomeSnapshot(id="current", name="policy", version=2, season="test", score=1.0, matches=10),
        baseline=OutcomeSnapshot(id="base", name="policy", version=1, season="test", score=0.9, matches=12),
    )
    failures = FailureSummary(total_episodes=10, completed_episodes=8, failed_episodes=2, failed_rate=0.2)

    action = compute_action_summary(outcome, failures)

    assert action.rollout_recommendation == "block"
    assert "reliability" in action.headline.lower()


def test_create_state_page_router_exposes_dashboard_data_and_analysis_routes() -> None:
    router = state_page_router.create_state_page_router()
    route_paths = {route.path for route in router.routes if isinstance(route, APIRoute)}

    assert "/stats/policies/versions/{policy_version_id}/dashboard-data" in route_paths
    assert "/stats/policies/versions/{policy_version_id}/dashboard-analysis" in route_paths


def test_state_page_routes_require_softmax_user() -> None:
    def has_softmax_dep(endpoint: object) -> bool:
        hints = typing.get_type_hints(endpoint, include_extras=True)
        for name, hint in hints.items():
            if name == "return":
                continue
            for arg in typing.get_args(hint):
                if isinstance(arg, Depends) and arg.dependency is get_softmax_user_or_raise:
                    return True
        return False

    router = state_page_router.create_state_page_router()
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        assert has_softmax_dep(route.endpoint), f"Route {route.path} is missing SoftmaxUser auth dependency"


def test_state_page_routes_are_internal_only_in_docs() -> None:
    app = create_app()
    public_spec = app.openapi()
    internal_spec = get_openapi(title=app.title, version=app.version, routes=app.routes)
    state_page_paths = {
        "/stats/policies/versions/{policy_version_id}/dashboard-data",
        "/stats/policies/versions/{policy_version_id}/dashboard-analysis",
    }

    for path in state_page_paths:
        assert path not in public_spec["paths"]
        assert path in internal_spec["paths"]


def test_compute_opponent_metrics_includes_precomputed_kpi_keys() -> None:
    episodes = [
        DashboardEpisode(
            episode_id="ep-1",
            job_id="job-1",
            opponent_name="opp-a",
            opponent_version=1,
            team_composition="4v4",
            reward=1.0,
            status="completed",
            steps=100,
            metrics={
                "action.move.success": 8,
                "action.move.failed": 2,
                "action.noop.success": 1,
                "action.failed": 1,
                "junction.aligned_by_agent": 3,
                "junction.scrambled_by_agent": 1,
                "carbon.amount": 4,
                "carbon.gained": 5,
            },
        )
    ]

    metrics_by_opponent = compute_opponent_metrics(episodes)
    avg_metrics = metrics_by_opponent["opp-a"].avg_metrics

    assert "kpi.move_efficiency" in avg_metrics
    assert "kpi.action_success_rate" in avg_metrics
    assert "kpi.resource_retention" in avg_metrics
    assert "kpi.junction_control_rate" in avg_metrics
    assert "kpi.noop_rate" in avg_metrics
