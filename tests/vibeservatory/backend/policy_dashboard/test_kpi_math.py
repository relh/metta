from __future__ import annotations

from vibeservatory.backend.dashboard_backend.policy_dashboard.kpi_math import (
    action_success_total,
    metric_presence_aliases,
    metric_present,
    noop_rate,
)


def test_action_success_total_counts_action_move_alias() -> None:
    metrics = {
        "action.move": 12.0,
        "action.noop.success": 3.0,
    }

    assert action_success_total(metrics) == 15.0
    assert noop_rate(metrics) == 0.2


def test_action_move_failed_presence_requires_specific_failed_metric() -> None:
    metrics = {
        "action.move": 12.0,
    }

    assert metric_present(metrics, "action.move.success")
    assert not metric_present(metrics, "action.move.failed")
    assert metric_presence_aliases("action.move.failed") == ("action.move.failed",)
