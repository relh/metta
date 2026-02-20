from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from devops.datadog.datadog_client import DatadogMetricsClient
from devops.datadog.models import MetricSample, ServiceCheckSample
from devops.runners.core import Job, JobStatus, Runner
from devops.stable.stable_check_lifecycle import DEFAULT_LIFECYCLE, NON_BLOCKING_LIFECYCLES, StableCheckLifecycle
from devops.stable.stable_check_metrics import (
    STABLE_CHECK_COMPLETED_AT_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK,
    STABLE_CHECK_RAW_STATUS_METRIC,
    job_path_to_job_tag,
)

logger = logging.getLogger(__name__)


def _get_job_path(job: Job, /) -> str | None:
    """Extract job path from job command.

    Job commands are like:

    - Local:
        ["uv", "run", "./tools/run.py", "recipes.prod.arena_basic_easy_shaped.train_100m", ...]
    - Remote:
        ["uv", "run", "./devops/skypilot/launch.py", "recipes.prod.arena_basic_easy_shaped.train_100m", ...]
    - Stable function check:
        ["uv", "run", "./tools/run.py", "devops.stable.stable_function_check_tool.run_check_tool",
         "check_path=<dotted.module.path.to.check_function>"]

    Returns the recipe path (e.g., "recipes.prod.arena_basic_easy_shaped.train_100m") or
    function check path (e.g., "devops.stable.function_checks.softmaxdotcom.healthcheck")
    or None if not found.
    """
    if not job.cmd or len(job.cmd) < 4:
        return None

    # The recipe path is always the 4th element (index 3) in the command
    recipe_path = job.cmd[3]
    if recipe_path.startswith("recipes."):
        return recipe_path

    # Function checks pass the original check path as a key=value argument.
    for arg in job.cmd[4:]:
        if arg.startswith("check_path="):
            return arg.split("=", 1)[1]

    return None


def _normalize_acceptance_criterion_name(name: str, /) -> str:
    """Normalize criterion metric name for tagging.

    Examples:
        "overview/sps" -> "overview_sps"
        "env_agent/heart.gained" -> "env_agent_heart_gained"
    """
    return name.replace("/", "_").replace(".", "_")


def _get_job_completed_at(job: Job) -> datetime:
    completed_at = job.completed_at or datetime.now(timezone.utc)
    return completed_at.astimezone(timezone.utc)


def _get_job_terminal_status(job: Job, /, *, success: bool) -> tuple[float, str]:
    if job.status == JobStatus.SKIPPED:
        return 0.0, JobStatus.SKIPPED.value
    if success:
        return 1.0, JobStatus.SUCCEEDED.value
    return -1.0, JobStatus.FAILED.value


def _effective_status_to_service_check_status(summary_status: float) -> tuple[int, str]:
    # Datadog service check status codes:
    # 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN.
    # Effective status comes from lifecycle-aware check semantics:
    # -1 blocking failure, 0 non-blocking, +1 success.
    # Non-blocking states (e.g. quarantined/not_implemented) are reported as OK
    # so they do not trigger failed-check paging monitors.
    if summary_status < 0:
        return 2, JobStatus.FAILED.value
    if summary_status > 0:
        return 0, JobStatus.SUCCEEDED.value
    return 0, "non_blocking"


def _get_job_metadata_lifecycle(job: Job) -> StableCheckLifecycle:
    value = job.metadata.get("lifecycle", DEFAULT_LIFECYCLE.value)
    return StableCheckLifecycle(value)


def _get_job_summary_status(lifecycle: StableCheckLifecycle, success: bool) -> float:
    if lifecycle in NON_BLOCKING_LIFECYCLES:
        return 0.0
    return 1.0 if success else -1.0


def _job_to_metrics(job: Job) -> list[MetricSample]:
    """Convert a Job result to Datadog MetricSamples using unified acceptance schema.

    Emits triples (value, target, status) for:
    - runs_success: Whether the job succeeded overall
    - Each acceptance criterion defined on the job

    Args:
        job: Completed job from the runner.

    Returns:
        List of MetricSamples ready to submit to Datadog.
    """

    samples: list[MetricSample] = []

    job_path = _get_job_path(job)
    if not job_path:
        logger.debug("Skipping job %s: could not extract job tag from command", job.name)
        return samples

    # New metrics use cleaned job tag (no "recipes." prefix)
    job_tag = job_path_to_job_tag(job_path)
    # Legacy metrics use old job tag (with "recipes_" prefix) for backward compat.
    legacy_job_tag = job_path.replace(".", "_")

    # Extract data from the job.
    datadog_metric_category = str(job.metadata["datadog_metric_category"])
    check_group = str(job.metadata["check_group"])
    lifecycle = _get_job_metadata_lifecycle(job)
    success = job.status == JobStatus.SUCCEEDED and job.acceptance_passed is not False
    terminal_status_value, terminal_status_name = _get_job_terminal_status(job, success=success)
    completed_at = _get_job_completed_at(job)
    summary_status = _get_job_summary_status(lifecycle, success)

    # Build base tags.
    base_tags = {
        "job_name": job.name,
        "lifecycle": lifecycle.value,
    }
    if check_group:
        base_tags["check_group"] = check_group
    if job.is_remote:
        base_tags["execution_type"] = "remote"
        base_tags["gpus"] = str(job.remote_gpus)
        base_tags["nodes"] = str(job.remote_nodes)
    else:
        base_tags["execution_type"] = "local"

    check_level_metric_tags = {
        "job": job_tag,
        "category": datadog_metric_category,
        "lifecycle": lifecycle.value,
        "terminal_status": terminal_status_name,
        **base_tags,
    }

    # Emit check-level metrics.
    samples.append(
        MetricSample(
            name=STABLE_CHECK_RAW_STATUS_METRIC,
            value=terminal_status_value,
            tags=check_level_metric_tags,
            timestamp=completed_at,
        )
    )
    samples.append(
        MetricSample(
            name=STABLE_CHECK_EFFECTIVE_STATUS_METRIC,
            value=summary_status,
            tags=check_level_metric_tags,
            timestamp=completed_at,
        )
    )
    samples.append(
        MetricSample(
            name=STABLE_CHECK_COMPLETED_AT_METRIC,
            value=float(completed_at.timestamp()),
            tags=check_level_metric_tags,
            timestamp=completed_at,
        )
    )

    # Emit runs_success criterion (always emitted for completed jobs)
    samples.extend(
        MetricSample.from_criterion(
            job=job_tag,
            category=datadog_metric_category,
            criterion="runs_success",
            value=1.0 if success else 0.0,
            target=1.0,
            operator=">=",
            passed=success,
            base_tags=base_tags,
        )
    )
    # TODO(datadog-migration): Remove legacy metric after dashboard migration (2025-02-01)
    samples.append(
        MetricSample(
            name=f"metta.infra.cron.stable.{legacy_job_tag}.runs_success",
            value=1.0 if success else 0.0,
            tags=base_tags,
        )
    )

    # Emit metrics for each acceptance criterion.
    if job.acceptance and job.status == JobStatus.SUCCEEDED and job.metrics:
        for criterion in job.acceptance:
            actual_value = job.metrics.get(criterion.metric)
            if actual_value is None:
                logger.debug(
                    "Skipping criterion %s for job %s: metric not found in job.metrics",
                    criterion.metric,
                    job.name,
                )
                continue

            criterion_passed = job.criterion_results.get(criterion.metric, False)
            criterion_name = _normalize_acceptance_criterion_name(criterion.metric)

            # Build criterion-specific tags
            criterion_tags = dict(base_tags)

            # Handle tuple thresholds (for "in" operator)
            if isinstance(criterion.threshold, tuple):
                target_low, target_high = criterion.threshold
                # Use upper bound for target line overlay
                target_value = float(target_high)
                # Preserve range bounds in tags
                criterion_tags["target_low"] = str(target_low)
                criterion_tags["target_high"] = str(target_high)
            else:
                target_value = float(criterion.threshold)

            samples.extend(
                MetricSample.from_criterion(
                    job=job_tag,
                    category=datadog_metric_category,
                    criterion=criterion_name,
                    value=float(actual_value),
                    target=target_value,
                    operator=criterion.operator,
                    passed=criterion_passed,
                    base_tags=criterion_tags,
                )
            )

            # TODO(datadog-migration): Remove legacy metric after dashboard migration (2025-02-01)
            samples.append(
                MetricSample(
                    name=f"metta.infra.cron.stable.{legacy_job_tag}.{criterion_name}",
                    value=float(actual_value),
                    tags={
                        **base_tags,
                        "criterion_passed": str(criterion_passed).lower(),
                        "criterion_threshold": str(criterion.threshold),
                        "criterion_operator": criterion.operator,
                    },
                )
            )

    return samples


def _jobs_to_metrics(jobs: dict[str, Job]) -> list[MetricSample]:
    """Convert all job results to Datadog metrics.

    Args:
        jobs: Dictionary of job name to Job result.

    Returns:
        List of all MetricSamples from all jobs.
    """
    all_samples: list[MetricSample] = []
    for job in jobs.values():
        samples = _job_to_metrics(job)
        all_samples.extend(samples)
    return all_samples


def _job_to_effective_status_service_check(job: Job) -> ServiceCheckSample | None:
    job_path = _get_job_path(job)
    if not job_path:
        logger.debug("Skipping service check for job %s: could not extract job tag from command", job.name)
        return None

    job_tag = job_path_to_job_tag(job_path)
    lifecycle = _get_job_metadata_lifecycle(job)
    success = job.status == JobStatus.SUCCEEDED and job.acceptance_passed is not False
    summary_status = _get_job_summary_status(lifecycle, success)
    effective_service_check_status, effective_status_name = _effective_status_to_service_check_status(summary_status)
    datadog_metric_category = str(job.metadata["datadog_metric_category"])
    check_group = str(job.metadata["check_group"])
    completed_at = _get_job_completed_at(job)

    tags = {
        "job": job_tag,
        "category": datadog_metric_category,
        "lifecycle": lifecycle.value,
    }
    if check_group:
        tags["check_group"] = check_group

    return ServiceCheckSample(
        check=STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK,
        status=effective_service_check_status,
        tags=tags,
        message=f"effective_status={effective_status_name}",
        host_name="stable-check-runner",
        timestamp=completed_at,
    )


def _jobs_to_service_checks(jobs: dict[str, Job]) -> list[ServiceCheckSample]:
    checks: list[ServiceCheckSample] = []
    for job in jobs.values():
        effective_check = _job_to_effective_status_service_check(job)
        if effective_check is not None:
            checks.append(effective_check)
    return checks


def report_datadog_metrics(
    client: Optional[DatadogMetricsClient], runner: Runner, skip: bool = False, dump: Optional[Path] = None
):
    """Emit Datadog metrics and service checks for completed jobs"""
    metrics = _jobs_to_metrics(runner.jobs)
    service_checks = _jobs_to_service_checks(runner.jobs)
    if not metrics and not service_checks:
        logger.debug("No metrics or service checks")
        return

    # Dump metrics to file if requested
    if dump:
        payload = [m.to_dict() for m in metrics]
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(json.dumps(payload, indent=2))
        print(f"\nWrote {len(metrics)} metrics to {dump}")

    if skip:
        logger.info(
            "Skipping submission of %d Datadog metrics and %d service checks from job results",
            len(metrics),
            len(service_checks),
        )
        return

    if client is None:
        raise TypeError("Datadog reporter expected DatadogMetricsClient, received None")

    if metrics:
        logger.info("Emitting %d Datadog metrics from job results", len(metrics))
        client.submit(metrics)
    if service_checks:
        logger.info("Emitting %d Datadog service checks from job results", len(service_checks))
        client.submit_service_checks(service_checks)
    logger.info("Successfully emitted Datadog telemetry")
