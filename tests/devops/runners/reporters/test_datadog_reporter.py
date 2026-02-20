from __future__ import annotations

from datetime import datetime, timezone

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


def test_job_to_metrics_marks_failed_when_acceptance_fails() -> None:
    job = _make_job(status=JobStatus.SUCCEEDED, acceptance_passed=False)
    samples = _job_to_metrics(job)

    terminal = _first_metric(samples, STABLE_CHECK_RAW_STATUS_METRIC)
    assert terminal.value == -1.0
    assert terminal.tags["terminal_status"] == "failed"


def test_job_to_metrics_marks_skipped_terminal_status() -> None:
    job = _make_job(status=JobStatus.SKIPPED)
    samples = _job_to_metrics(job)

    terminal = _first_metric(samples, STABLE_CHECK_RAW_STATUS_METRIC)
    assert terminal.value == 0.0
    assert terminal.tags["terminal_status"] == "skipped"


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


def test_job_to_metrics_marks_quarantined_as_yellow_summary() -> None:
    job = _make_job(status=JobStatus.FAILED)
    job.metadata["lifecycle"] = "quarantined"
    samples = _job_to_metrics(job)

    summary = _first_metric(samples, STABLE_CHECK_EFFECTIVE_STATUS_METRIC)
    assert summary.value == 0.0
    assert summary.tags["lifecycle"] == "quarantined"


def test_job_to_metrics_marks_active_failure_as_red_summary() -> None:
    job = _make_job(status=JobStatus.FAILED)
    samples = _job_to_metrics(job)

    summary = _first_metric(samples, STABLE_CHECK_EFFECTIVE_STATUS_METRIC)
    assert summary.value == -1.0
    assert summary.tags["lifecycle"] == "active"


def test_job_to_effective_status_service_check_marks_failed_as_critical() -> None:
    job = _make_job(status=JobStatus.FAILED)
    check = _job_to_effective_status_service_check(job)
    assert check is not None
    assert check.check == STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK
    assert check.status == 2
    assert check.tags["job"] == "prod_arena_basic_easy_shaped_train_100m"


def test_job_to_effective_status_service_check_marks_succeeded_as_ok() -> None:
    job = _make_job(status=JobStatus.SUCCEEDED, acceptance_passed=True)
    check = _job_to_effective_status_service_check(job)
    assert check is not None
    assert check.status == 0


def test_job_to_effective_status_service_check_marks_skipped_as_critical() -> None:
    job = _make_job(status=JobStatus.SKIPPED)
    check = _job_to_effective_status_service_check(job)
    assert check is not None
    assert check.status == 2


def test_job_to_effective_status_service_check_marks_quarantined_failure_as_ok() -> None:
    job = _make_job(status=JobStatus.FAILED)
    job.metadata["lifecycle"] = "quarantined"
    check = _job_to_effective_status_service_check(job)
    assert check is not None
    assert check.status == 0
