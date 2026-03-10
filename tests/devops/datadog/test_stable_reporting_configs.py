from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import devops.datadog.dashboards as dashboards
import devops.datadog.monitors as monitors
from devops.stable.stable_check_groups import StableCheckGroup
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


def _iter_widgets(widgets: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for widget in widgets:
        flattened.append(widget)
        nested_widgets = widget["definition"].get("widgets", [])
        flattened.extend(_iter_widgets(nested_widgets))
    return flattened


def test_stable_dashboard_exists_with_expected_queries() -> None:
    configs = dashboards.get_all_dashboard_configs()
    stable = next(config for config in configs if config["title"] == "Stable Runner V2")
    all_widgets = _iter_widgets(stable["widgets"])
    titles = {widget["definition"].get("title") for widget in all_widgets}
    note_contents = {
        widget["definition"].get("content") for widget in all_widgets if widget["definition"].get("type") == "note"
    }
    query_bits: list[str] = []
    for widget in all_widgets:
        for request in widget["definition"].get("requests", []):
            maybe_q = request.get("q")
            if maybe_q:
                query_bits.append(maybe_q)
            for query in request.get("queries", []):
                maybe_query = query.get("query")
                if maybe_query:
                    query_bits.append(maybe_query)
        monitor_query = widget["definition"].get("query")
        if monitor_query:
            query_bits.append(monitor_query)
    query_text = "\n".join(query_bits)

    assert "Stable Runner Checks" in note_contents
    assert "Episode + Job Runtime Health" in note_contents
    assert "Managed Monitors" in note_contents
    assert "Stable Runner - Key Metrics" in titles
    assert "Failure Breakdown" in titles
    assert "Stage Durations (p50 / p90)" in titles
    assert "Concurrent Running Jobs" in titles
    assert "Job Status Transitions (count)" in titles
    assert "Episode Length (10m avg)" in titles
    assert "Episode Length Trend (episode jobs)" in titles
    assert "API Requests (10m sum)" in titles
    assert "API 5xx Density (10m %)" in titles
    assert "API Latency Avg (10m s)" in titles
    assert "CrashLoopBackOff Containers (10m max)" in titles
    assert "CrashLoopBackOff Top Namespaces" in titles
    assert "CrashLoopBackOff Top Pods" in titles
    assert "Stable Monitor Alerts" in titles
    assert "Non-Stable Monitor Alerts" in titles
    assert STABLE_CHECK_RAW_STATUS_METRIC in query_text
    assert STABLE_CHECK_EFFECTIVE_STATUS_METRIC in query_text
    assert STABLE_CHECK_COMPLETED_AT_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_VALUE_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC in query_text
    assert "service:observatory-backend,env:production,job_type:episode" in query_text
    assert "avg:job.running_count" in query_text
    assert "p50:job.stage_duration" in query_text
    assert "p90:job.stage_duration" in query_text
    assert "to_status:completed" in query_text
    assert "to_status:running" in query_text
    assert "to_status:dispatched" in query_text
    assert "to_status:failed" in query_text
    assert "by {error_type}.as_count().rollup(sum, 60)" in query_text
    assert "episode.length" in query_text
    assert "http.server.request.count" in query_text
    assert "http.server.request.duration" in query_text
    assert "http.status_code:5*" in query_text
    assert "reason:crashloopbackoff" in query_text
    assert "tag:service:stable-runner tag:managed-by:code" in query_text
    assert "tag:managed-by:code -tag:service:stable-runner" in query_text
    assert "criterion:runs_success" in query_text
    assert "'last', 'desc'" in query_text
    latest_summary = next(
        widget
        for widget in all_widgets
        if widget["definition"].get("title") == "Latest Summary Status by Job (-1=red,0=yellow,1=green)"
    )
    latest_summary_queries = latest_summary["definition"]["requests"][0]["queries"]
    assert latest_summary_queries[0]["query"] == f"max:{STABLE_CHECK_EFFECTIVE_STATUS_METRIC}{{*}} by {{job}}"
    assert latest_summary_queries[1]["query"] == f"max:{STABLE_CHECK_COMPLETED_AT_METRIC}{{*}} by {{job}}"
    non_stable_widgets = [
        widget
        for widget in all_widgets
        if widget["definition"].get("type") == "manage_status"
        and widget["definition"].get("query") == "tag:managed-by:code -tag:service:stable-runner"
    ]
    assert len(non_stable_widgets) == 1


def test_episode_recording_failures_monitor_config() -> None:
    config = monitors.episode_recording_failures_monitor()
    assert config["name"] == monitors.TOURNAMENT_EPISODE_RECORDING_FAILURES_MONITOR_NAME
    assert config["type"] == "log alert"
    assert "service:k8s-event-processor" in config["query"]
    assert "env:production" in config["query"]
    assert "Failed to record episode for job" in config["query"]
    assert '.last("5m") > 3' in config["query"]
    assert config["priority"] == 2
    assert config["thresholds"]["critical"] == 3
    assert monitors.WEBHOOK_TOURNAMENT_ALERTS in config["message"]


def test_observatory_api_monitors_config() -> None:
    error_density = monitors.observatory_api_5xx_density_monitor()
    assert error_density["type"] == "query alert"
    assert "http.server.request.count" in error_density["query"]
    assert "http.status_code:5*" in error_density["query"]
    assert "service:observatory-backend,env:production" in error_density["query"]
    assert error_density["thresholds"]["critical"] == 5
    assert monitors.WEBHOOK_TOURNAMENT_ALERTS in error_density["message"]

    reachability = monitors.observatory_api_reachability_drop_monitor()
    assert reachability["type"] == "query alert"
    assert "http.server.request.count" in reachability["query"]
    assert "service:observatory-backend,env:production" in reachability["query"]
    assert "< 5" in reachability["query"]
    assert reachability["thresholds"]["critical"] == 5
    assert monitors.WEBHOOK_TOURNAMENT_ALERTS in reachability["message"]


def test_k8s_crashloopbackoff_monitor_pages_on_call() -> None:
    config = monitors.k8s_crashloopbackoff_monitor()
    assert config["type"] == "query alert"
    assert "reason:crashloopbackoff" in config["query"]
    assert "!kube_namespace:monitoring" in config["query"]
    assert monitors.WEBHOOK_DISCORD in config["message"]
    assert monitors.WEBHOOK_ONCALL in config["message"]


def test_monitor_names_are_unique() -> None:
    configs = monitors.get_all_monitor_configs()
    counts = Counter(config["name"] for config in configs)
    duplicates = {name: count for name, count in counts.items() if count > 1}
    assert not duplicates, f"Duplicate monitor names found: {duplicates}"


def test_stable_monitors_generated_per_job(monkeypatch) -> None:
    monkeypatch.setattr(
        monitors,
        "discover_stable_checks",
        lambda: [
            SimpleNamespace(
                func=SimpleNamespace(__module__="recipes.prod.job_a", __name__="check"),
                lifecycle=StableCheckLifecycle.ACTIVE,
                check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
            ),
            SimpleNamespace(
                func=SimpleNamespace(__module__="recipes.prod.job_b", __name__="check"),
                lifecycle=StableCheckLifecycle.QUARANTINED,
                check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
            ),
            SimpleNamespace(
                func=SimpleNamespace(__module__="recipes.prod.job_c", __name__="check"),
                lifecycle=StableCheckLifecycle.ACTIVE,
                check_group=StableCheckGroup.INTERNAL_TRAINING_HEAVY,
            ),
        ],
    )

    configs = monitors.get_all_monitor_configs()
    names = {config["name"] for config in configs}
    assert "[Stable] prod_job_a_check stale (28h)" in names
    assert "[Stable] prod_job_a_check latest failed" in names
    assert "[Stable] prod_job_b_check stale (28h)" not in names
    assert "[Stable] prod_job_b_check latest failed" not in names
    assert "[Stable] prod_job_c_check stale (28h)" not in names
    assert "[Stable] prod_job_c_check latest failed" not in names

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
