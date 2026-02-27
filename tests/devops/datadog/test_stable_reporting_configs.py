from __future__ import annotations

from types import SimpleNamespace

import devops.datadog.dashboards as dashboards
import devops.datadog.monitors as monitors
from devops.stable.stable_check_lifecycle import StableCheckLifecycle
from devops.stable.stable_check_metrics import (
    STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC,
    STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC,
    STABLE_CHECK_ACCEPTANCE_CRITERION_VALUE_METRIC,
    STABLE_CHECK_COMPLETED_AT_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK,
    STABLE_CHECK_RAW_STATUS_METRIC,
)


def test_stable_dashboard_exists_with_expected_queries() -> None:
    configs = dashboards.get_all_dashboard_configs()
    stable = next(config for config in configs if config["title"] == "Stable Runner V2")
    query_bits: list[str] = []
    for widget in stable["widgets"]:
        for request in widget["definition"]["requests"]:
            maybe_q = request.get("q")
            if maybe_q:
                query_bits.append(maybe_q)
            for query in request.get("queries", []):
                maybe_query = query.get("query")
                if maybe_query:
                    query_bits.append(maybe_query)
    query_text = "\n".join(query_bits)

    assert any(widget["definition"]["title"] == "Stable Runner - Key Metrics" for widget in stable["widgets"])
    assert any(widget["definition"]["title"] == "Failure Breakdown" for widget in stable["widgets"])
    assert any(widget["definition"]["title"] == "Stage Durations (p50 / p90)" for widget in stable["widgets"])
    assert any(widget["definition"]["title"] == "Concurrent Running Jobs" for widget in stable["widgets"])
    assert any(widget["definition"]["title"] == "Job Status Transitions (count)" for widget in stable["widgets"])
    assert any(widget["definition"]["title"] == "Episode Length (10m avg)" for widget in stable["widgets"])
    assert any(widget["definition"]["title"] == "Episode Length Trend (episode jobs)" for widget in stable["widgets"])
    assert STABLE_CHECK_RAW_STATUS_METRIC in query_text
    assert STABLE_CHECK_EFFECTIVE_STATUS_METRIC in query_text
    assert STABLE_CHECK_COMPLETED_AT_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_VALUE_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC in query_text
    assert "service:observatory-backend,env:production,job_type:episode" in query_text
    assert "sum:job.running_count" in query_text
    assert "p50:job.stage_duration" in query_text
    assert "p90:job.stage_duration" in query_text
    assert "to_status:completed" in query_text
    assert "to_status:running" in query_text
    assert "to_status:dispatched" in query_text
    assert "to_status:failed" in query_text
    assert "by {error_type}.as_count().rollup(sum, 60)" in query_text
    assert "episode.length" in query_text
    assert "service:observatory-backend,job_type:episode" in query_text
    assert "criterion:runs_success" in query_text
    assert "'last', 'desc'" in query_text
    assert any(
        widget["definition"]["title"] == "Latest Summary Status by Job (-1=red,0=yellow,1=green)"
        for widget in stable["widgets"]
    )
    latest_summary = next(
        widget
        for widget in stable["widgets"]
        if widget["definition"]["title"] == "Latest Summary Status by Job (-1=red,0=yellow,1=green)"
    )
    latest_summary_queries = latest_summary["definition"]["requests"][0]["queries"]
    assert latest_summary_queries[0]["query"] == f"last:{STABLE_CHECK_EFFECTIVE_STATUS_METRIC}{{*}} by {{job}}"
    assert latest_summary_queries[1]["query"] == f"last:{STABLE_CHECK_COMPLETED_AT_METRIC}{{*}} by {{job}}"


def test_stable_monitors_generated_per_job(monkeypatch) -> None:
    monkeypatch.setattr(
        monitors,
        "discover_stable_checks",
        lambda: [
            SimpleNamespace(
                func=SimpleNamespace(__module__="recipes.prod.job_a", __name__="check"),
                lifecycle=StableCheckLifecycle.ACTIVE,
            ),
            SimpleNamespace(
                func=SimpleNamespace(__module__="recipes.prod.job_b", __name__="check"),
                lifecycle=StableCheckLifecycle.QUARANTINED,
            ),
        ],
    )

    configs = monitors.get_all_monitor_configs()
    names = {config["name"] for config in configs}
    assert "[Stable] prod_job_a_check stale (28h)" in names
    assert "[Stable] prod_job_a_check latest failed" in names
    assert "[Stable] prod_job_b_check stale (28h)" not in names
    assert "[Stable] prod_job_b_check latest failed" not in names

    stable_configs = [config for config in configs if config["name"].startswith("[Stable] ")]
    assert len(stable_configs) == 2
    for config in stable_configs:
        assert "scope:testing" in config["tags"]
        assert monitors.WEBHOOK_STABLE_ALERTS in config["message"]

    stale_monitor = next(config for config in stable_configs if config["name"].endswith("stale (28h)"))
    assert stale_monitor["type"] == "query alert"
    assert f"avg({monitors.STABLE_STALE_QUERY_LOOKBACK})" in stale_monitor["query"]
    assert "default_zero(" in stale_monitor["query"]
    assert STABLE_CHECK_COMPLETED_AT_METRIC in stale_monitor["query"]
    assert "{job:prod_job_a_check}" in stale_monitor["query"]
    assert stale_monitor["query"].endswith(" < 1")
    assert stale_monitor["thresholds"]["critical"] == 1
    assert stale_monitor["options"]["notify_no_data"] is False
    assert stale_monitor["options"]["require_full_window"] is False
    assert "no_data_timeframe" not in stale_monitor["options"]

    failed_monitor = next(config for config in stable_configs if config["name"].endswith("latest failed"))
    assert failed_monitor["type"] == "service check"
    assert STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK in failed_monitor["query"]
    assert f".last({monitors.STABLE_FAILED_SERVICE_CHECK_LAST_COUNT}).count_by_status()" in failed_monitor["query"]
    assert '.over("job:prod_job_a_check")' in failed_monitor["query"]
