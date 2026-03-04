from __future__ import annotations

from datetime import datetime, timezone

import pytest

from devops.runners.executors.local import LocalExecutor
from devops.runners.job import Job, JobStatus
from devops.runners.reporters.datadog import _job_to_effective_status_service_check, _job_to_metrics
from devops.stable.stable_check_metrics import (
    STABLE_CHECK_COMPLETED_AT_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK,
    STABLE_CHECK_RAW_STATUS_METRIC,
)


def _make_job(*, status: JobStatus, acceptance_passed: bool | None = None) -> Job:
    completed_at = datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc)
    return Job(
        name="runner.stable.2026-arena.train_100m",
        cmd=["uv", "run", "./tools/run.py", "recipes.prod.arena_basic_easy_shaped.train_100m"],
        executor=LocalExecutor(),
        metadata={
            "datadog_metric_category": "training",
            "check_group": "internal_training_heavy",
            "lifecycle": "active",
        },
        status=status,
        acceptance_passed=acceptance_passed,
        completed_at=completed_at,
    )


def _first_metric(samples: list, name: str):
    return next(sample for sample in samples if sample.name == name)


def test_job_to_metrics_emits_last_completion_timestamp() -> None:
    job = _make_job(status=JobStatus.SUCCEEDED, acceptance_passed=True)
    samples = _job_to_metrics(job)

    completion = _first_metric(samples, STABLE_CHECK_COMPLETED_AT_METRIC)
    assert completion.value == float(job.completed_at.timestamp())
    assert completion.tags["job"] == "prod_arena_basic_easy_shaped_train_100m"
    assert completion.tags["check_group"] == "internal_training_heavy"


@pytest.mark.parametrize(
    ("status", "acceptance_passed", "expected_value", "expected_terminal_status"),
    [
        (JobStatus.SUCCEEDED, False, -1.0, "failed"),
        (JobStatus.SKIPPED, None, 0.0, "skipped"),
    ],
    ids=["acceptance-failed", "skipped"],
)
def test_job_to_metrics_terminal_status_mapping(
    status: JobStatus,
    acceptance_passed: bool | None,
    expected_value: float,
    expected_terminal_status: str,
) -> None:
    job = _make_job(status=status, acceptance_passed=acceptance_passed)
    samples = _job_to_metrics(job)

    terminal = _first_metric(samples, STABLE_CHECK_RAW_STATUS_METRIC)
    assert terminal.value == expected_value
    assert terminal.tags["terminal_status"] == expected_terminal_status


def test_job_to_metrics_supports_function_check_command() -> None:
    job = _make_job(status=JobStatus.SUCCEEDED, acceptance_passed=True)
    job.cmd = [
        "uv",
        "run",
        "./tools/run.py",
        "devops.stable.stable_function_check_tool.run_check_tool",
        "check_path=devops.stable.function_checks.softmaxdotcom.healthcheck",
    ]

    samples = _job_to_metrics(job)
    completion = _first_metric(samples, STABLE_CHECK_COMPLETED_AT_METRIC)
    assert completion.tags["job"] == "prod_softmaxdotcom_healthcheck"


def test_job_to_metrics_emits_summary_metrics() -> None:
    job = _make_job(status=JobStatus.SUCCEEDED, acceptance_passed=True)
    samples = _job_to_metrics(job)

    summary = _first_metric(samples, STABLE_CHECK_EFFECTIVE_STATUS_METRIC)
    summary_ts = _first_metric(samples, STABLE_CHECK_COMPLETED_AT_METRIC)
    assert summary.value == 1.0
    assert summary_ts.value == float(job.completed_at.timestamp())
    assert summary.tags["lifecycle"] == "active"
    assert summary_ts.tags["job"] == "prod_arena_basic_easy_shaped_train_100m"


@pytest.mark.parametrize(
    ("status", "acceptance_passed", "lifecycle", "expected_value"),
    [
        (JobStatus.SUCCEEDED, True, "active", 1.0),
        (JobStatus.FAILED, None, "quarantined", 0.0),
        (JobStatus.FAILED, None, "active", -1.0),
    ],
    ids=["active-success", "quarantined-failure", "active-failure"],
)
def test_job_to_metrics_effective_summary_mapping(
    status: JobStatus,
    acceptance_passed: bool | None,
    lifecycle: str,
    expected_value: float,
) -> None:
    job = _make_job(status=status, acceptance_passed=acceptance_passed)
    job.metadata["lifecycle"] = lifecycle
    samples = _job_to_metrics(job)

    summary = _first_metric(samples, STABLE_CHECK_EFFECTIVE_STATUS_METRIC)
    assert summary.value == expected_value
    assert summary.tags["lifecycle"] == lifecycle


@pytest.mark.parametrize(
    ("status", "acceptance_passed", "lifecycle", "expected_status"),
    [
        (JobStatus.FAILED, None, "active", 2),
        (JobStatus.SUCCEEDED, True, "active", 0),
        (JobStatus.SKIPPED, None, "active", 2),
        (JobStatus.FAILED, None, "quarantined", 0),
    ],
    ids=["failed-critical", "succeeded-ok", "skipped-critical", "quarantined-ok"],
)
def test_job_to_effective_status_service_check_mapping(
    status: JobStatus,
    acceptance_passed: bool | None,
    lifecycle: str,
    expected_status: int,
) -> None:
    job = _make_job(status=status, acceptance_passed=acceptance_passed)
    job.metadata["lifecycle"] = lifecycle
    check = _job_to_effective_status_service_check(job)

    assert check is not None
    assert check.check == STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK
    assert check.status == expected_status
    assert check.tags["job"] == "prod_arena_basic_easy_shaped_train_100m"
