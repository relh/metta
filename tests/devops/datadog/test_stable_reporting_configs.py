from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import devops.datadog.monitors as monitors
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_check_lifecycle import StableCheckLifecycle
from devops.stable.stable_check_metrics import (
    STABLE_CHECK_COMPLETED_AT_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK,
)


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


def test_tournament_progress_monitors_config() -> None:
    dispatch_drop = monitors.tournament_dispatch_activity_drop_monitor()
    assert dispatch_drop["type"] == "query alert"
    assert "to_status:dispatched" in dispatch_drop["query"]
    assert "service:observatory-backend,env:production,job_type:episode" in dispatch_drop["query"]
    assert dispatch_drop["thresholds"]["critical"] == 1
    assert monitors.WEBHOOK_TOURNAMENT_ALERTS in dispatch_drop["message"]

    dispatched_queue = monitors.job_dispatched_queue_stuck_monitor()
    assert dispatched_queue["type"] == "query alert"
    assert "job.outstanding_count" in dispatched_queue["query"]
    assert "status:dispatched" in dispatched_queue["query"]
    assert dispatched_queue["thresholds"]["critical"] == 25
    assert monitors.WEBHOOK_TOURNAMENT_ALERTS in dispatched_queue["message"]

    unscored = monitors.tournament_unscored_completed_matches_monitor()
    assert unscored["type"] == "query alert"
    assert "tournament.unscored_completed_matches" in unscored["query"]
    assert unscored["thresholds"]["critical"] == 10
    assert monitors.WEBHOOK_TOURNAMENT_ALERTS in unscored["message"]

    compat = monitors.latest_compat_runner_stale_monitor()
    assert compat["type"] == "query alert"
    assert "to_status:running" in compat["query"]
    assert f"compat_version:{monitors.LATEST_COMPAT_VERSION}" in compat["query"]
    assert compat["thresholds"]["critical"] == 1
    assert monitors.WEBHOOK_TOURNAMENT_ALERTS in compat["message"]


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
