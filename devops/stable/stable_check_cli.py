#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from devops.datadog.datadog_client import DatadogMetricsClient
from devops.runners.core import Runner
from devops.runners.job import Job, JobStatus
from devops.runners.reporters.datadog import report_datadog_metrics
from devops.runners.reporters.discord import write_discord_summary
from devops.runners.reporters.github import report_gh_step_summary
from devops.runners.reporters.shared import build_categorized_jobs
from devops.runners.reporters.stdout import print_failed_logs
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_check_lifecycle import NON_BLOCKING_LIFECYCLES, StableCheckLifecycle
from devops.stable.stable_check_registry import discover_stable_checks, stable_check_configs_to_jobs

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, invoke_without_command=True)


def _job_lifecycle(job: Job) -> StableCheckLifecycle:
    return StableCheckLifecycle(job.metadata["lifecycle"])


def _is_job_blocking_failure(job: Job) -> bool:
    return (job.status == JobStatus.FAILED or job.acceptance_passed is False) and _job_lifecycle(
        job
    ) not in NON_BLOCKING_LIFECYCLES


@app.callback()
def main(
    check_group: Annotated[
        list[StableCheckGroup] | None,
        typer.Option(
            "--check-group",
            help=(
                "Filter checks by group (repeatable). "
                "Allowed: internal_training_light, internal_training_heavy, live_tests_light, live_tests_heavy."
            ),
        ),
    ] = None,
    skip_submitting_metrics: Annotated[
        bool, typer.Option("--skip-submitting-metrics", help="Skip submitting metrics to Datadog")
    ] = False,
    dump_metrics: Annotated[
        Path | None, typer.Option("--dump-metrics", help="Write metrics JSON to file for inspection")
    ] = None,
):
    # Get Datadog client up front to fail fast in case of missing credentials
    datadog_client: DatadogMetricsClient | None = None
    if not skip_submitting_metrics:
        datadog_client = DatadogMetricsClient()

    parsed_check_groups = set(check_group or [])

    version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    user = os.environ.get("USER", "unknown")
    prefix = f"{user}.checks.{version}"
    state_dir = Path("devops/stable/state")

    check_configs = discover_stable_checks(check_groups=parsed_check_groups or None)
    if parsed_check_groups and not check_configs:
        group_text = ", ".join(sorted(group.value for group in parsed_check_groups))
        print(f"No jobs matched check groups: {group_text}")
        sys.exit(1)
    jobs = stable_check_configs_to_jobs(check_configs, prefix)

    runner = Runner(state_dir)
    for j in jobs:
        runner.add_job(j)
    for j in runner.jobs.values():
        if _job_lifecycle(j) is StableCheckLifecycle.NOT_IMPLEMENTED:
            j.status = JobStatus.SKIPPED
            j.exit_code = 0
            j.error = "Lifecycle not_implemented"

    print(f"Running checks: {version}")
    if parsed_check_groups:
        print(f"Check groups: {', '.join(sorted(group.value for group in parsed_check_groups))}")
    print(f"Jobs: {len(runner.jobs)}")
    for j in runner.jobs.values():
        remote = "remote" if j.is_remote else "local"
        print(f"  - {j.name} ({remote})")

    runner.run_all()

    report_datadog_metrics(datadog_client, runner, skip_submitting_metrics, dump_metrics)

    categorized_jobs = build_categorized_jobs(runner)

    print_failed_logs(categorized_jobs)
    write_discord_summary(categorized_jobs, state_dir)
    report_gh_step_summary(categorized_jobs, title="Stable Release Validation")

    blocking_failed_jobs = [job for job in categorized_jobs["failed"] if _is_job_blocking_failure(job)]
    non_blocking_failed_jobs = [job for job in categorized_jobs["failed"] if not _is_job_blocking_failure(job)]

    if non_blocking_failed_jobs:
        print("\nNon-blocking failed jobs:")
        for job in non_blocking_failed_jobs:
            print(f"  - {job.name} (lifecycle={_job_lifecycle(job).value})")

    sys.exit(0 if not blocking_failed_jobs else 1)


if __name__ == "__main__":
    app()
