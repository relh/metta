import os
from pathlib import Path

from devops.runners.reporters.shared import CategorizedJobs, job_status


def write_discord_summary(jobs: CategorizedJobs, state_dir: Path) -> None:
    all_jobs = jobs["failed"] + jobs["passed"] + jobs["skipped"]
    header = f"{len(jobs['passed'])} passed, {len(jobs['failed'])} failed, {len(jobs['skipped'])} skipped"
    table = []
    for job in all_jobs:
        name = job.name.split(".")[-1]
        duration = f"{job.duration_s:.0f}s" if job.duration_s else "-"
        table.append(f"{name:<40} {job_status(job):<10} {duration}")

    # Discord summary (file)
    state_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"**Jobs**: {header}", "", "```", *table, "```"]

    # Add failure details
    if jobs["failed"]:
        lines.append("")
        lines.append("**Failure Details:**")
        for job in jobs["failed"]:
            job_short_name = job.name.split(".")[-1]
            if job.acceptance_failures:
                lines.append(f"- `{job_short_name}`: acceptance criteria not met")
                for failure in job.acceptance_failures:
                    lines.append(f"  - {failure}")
            elif job.error:
                lines.append(f"- `{job_short_name}`: {job.error}")
            else:
                lines.append(f"- `{job_short_name}`: unknown error")

    gh_server = os.environ.get("GITHUB_SERVER_URL")
    gh_repo = os.environ.get("GITHUB_REPOSITORY")
    gh_run_id = os.environ.get("GITHUB_RUN_ID")
    if gh_server and gh_repo and gh_run_id:
        lines.append(f"\n<{gh_server}/{gh_repo}/actions/runs/{gh_run_id}>")
    (state_dir / "discord_summary.txt").write_text("\n".join(lines))
