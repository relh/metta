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
    assert STABLE_CHECK_RAW_STATUS_METRIC in query_text
    assert STABLE_CHECK_EFFECTIVE_STATUS_METRIC in query_text
    assert STABLE_CHECK_COMPLETED_AT_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_VALUE_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC in query_text
    assert STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC in query_text
    assert "criterion:runs_success" in query_text
    assert "'last', 'desc'" in query_text
    assert any(
        widget["definition"]["title"] == "Latest Summary Status by Job (-1=red,0=yellow,1=green)"
        for widget in stable["widgets"]
    )


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

    failed_monitor = next(config for config in stable_configs if config["name"].endswith("latest failed"))
    assert failed_monitor["type"] == "service check"
    assert STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK in failed_monitor["query"]
    assert f".last({monitors.STABLE_FAILED_SERVICE_CHECK_LAST_COUNT}).count_by_status()" in failed_monitor["query"]
    assert '.over("job:prod_job_a_check")' in failed_monitor["query"]
