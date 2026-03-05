import os
from pathlib import Path

from devops.runners.reporters.shared import CategorizedJobs, job_failed, job_status


def write_discord_summary(jobs: CategorizedJobs, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    run_title = os.environ.get("GITHUB_WORKFLOW", "Run Summary")

    num_passed = len(jobs["passed"])
    num_failed = len(jobs["failed"])
    num_skipped = len(jobs["skipped"])
    lines = [f"**{run_title}** (passed={num_passed}, failed={num_failed}, skipped={num_skipped})", ""]

    all_jobs = jobs["failed"] + jobs["passed"] + jobs["skipped"]

    for job in all_jobs:
        name = job.name.split(".")[-1]
        duration = f"{job.duration_s:.0f}s" if job.duration_s else "??"
        status = job_status(job)
        lines.append(f"**{name}** (t={duration}, status={status})")
        lines.append(f"> {job.description}")
        if job_failed(job):
            lines.append("")
            lines.append("*Error Details:*")
            if job.acceptance_failures:
                lines.append("- acceptance criteria not met")
                for failure in job.acceptance_failures:
                    lines.append(f"  - {failure}")
            elif job.error:
                lines.append(f"- {job.error}")
            else:
                lines.append(
                    "- Job failed without an explicit error message. "
                    "View the Action Run link below and download "
                    "log artifacts to inspect."
                )

    gh_server = os.environ.get("GITHUB_SERVER_URL")
    gh_repo = os.environ.get("GITHUB_REPOSITORY")
    gh_run_id = os.environ.get("GITHUB_RUN_ID")
    if gh_server and gh_repo and gh_run_id:
        lines.append(f"\n<{gh_server}/{gh_repo}/actions/runs/{gh_run_id}>")
    (state_dir / "discord_summary.txt").write_text("\n".join(lines))
