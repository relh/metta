from __future__ import annotations

from dashboard.backend.dashboard_backend.state_page.diagnostics import (
    DashboardEpisode,
    compute_derived_metrics,
    compute_instrumentation_validation,
    compute_unsupported_state,
)


def _episode_with_alias_metrics() -> DashboardEpisode:
    return DashboardEpisode(
        episode_id="ep-1",
        job_id="job-1",
        created_at="2026-02-22T00:00:00Z",
        replay_url="https://example.com/replay",
        opponent_name="opp",
        opponent_version=1,
        team_composition="1v1",
        reward=1.0,
        status="completed",
        steps=100,
        raw_tags={
            "assignments": "[0, 1]",
            "policy_version_ids": "['pv-a', 'pv-b']",
        },
        metrics={
            "action.move": 12.0,
            "action.move.failed": 0.0,
            "action.noop.success": 3.0,
            "junction.aligned": 4.0,
            "junction.scrambled": 1.0,
            "status.frozen.ticks": 2.0,
            "heart.gained": 6.0,
        },
    )


def test_compute_unsupported_state_accepts_alias_metric_names() -> None:
    unsupported = compute_unsupported_state([_episode_with_alias_metrics()])
    issue_codes = {issue.code for issue in unsupported.issues}

    assert "missing_metric::action.move.success" not in issue_codes
    assert "missing_metric::action.move.failed" not in issue_codes
    assert "missing_metric::junction.aligned_by_agent" not in issue_codes
    assert "missing_metric::junction.scrambled_by_agent" not in issue_codes


def test_compute_instrumentation_validation_accepts_alias_metric_names() -> None:
    summary = compute_instrumentation_validation([_episode_with_alias_metrics()])
    checks = {check.key: check for check in summary.checks}

    assert checks["action.move.success"].status == "pass"
    assert checks["action.move.failed"].status == "pass"
    assert checks["junction.aligned_by_agent"].status == "pass"
    assert checks["junction.scrambled_by_agent"].status == "pass"


def test_compute_derived_metrics_reads_alias_metric_values() -> None:
    derived = compute_derived_metrics([_episode_with_alias_metrics()])

    assert derived.move_efficiency == 1.0
    assert derived.junction_control_rate == 0.8
    assert derived.noop_rate == 0.2
