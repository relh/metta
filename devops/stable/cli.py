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
from devops.runners.reporters.datadog import report_datadog_metrics
from devops.runners.reporters.discord import write_discord_summary
from devops.runners.reporters.github import report_gh_step_summary
from devops.runners.reporters.shared import build_categorized_jobs
from devops.runners.reporters.stdout import print_failed_logs
from devops.stable.asana_bugs import check_blockers
from devops.stable.registry import Suite, discover_jobs, specs_to_jobs

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def main(
    suite: Annotated[Suite | None, typer.Option(help="Which jobs to run: ci, stable, or all")] = None,
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

    has_blockers = False
    if suite != Suite.CI:
        print("Checking for blocking bugs in Asana...")
        blocker_result = check_blockers()
        if blocker_result is False:
            print("\nBlocking bugs found. Will fail after running jobs.")
            has_blockers = True
        elif blocker_result is None:
            print("Asana check skipped (not configured or unavailable)")
        print()

    version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    user = os.environ.get("USER", "unknown")
    prefix = f"{user}.{suite or 'all'}.{version}"
    state_dir = Path("devops/stable/state")

    specs = discover_jobs(suite)
    jobs = specs_to_jobs(specs, prefix)

    runner = Runner(state_dir)
    for j in jobs:
        runner.add_job(j)

    print(f"Running {suite} jobs: {version}")
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

    if has_blockers:
        print("\nFAILED: Blocking bugs found in Asana")
        sys.exit(1)

    sys.exit(0 if not categorized_jobs["failed"] else 1)


if __name__ == "__main__":
    app()
