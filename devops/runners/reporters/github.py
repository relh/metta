import os

from devops.runners.reporters.shared import CategorizedJobs, job_status


def report_gh_step_summary(jobs: CategorizedJobs, title: str):
    gh_path = os.environ.get("GITHUB_STEP_SUMMARY")

    if gh_path:
        all_jobs = jobs["failed"] + jobs["passed"] + jobs["skipped"]
        header = f"{len(jobs['passed'])} passed, {len(jobs['failed'])} failed, {len(jobs['skipped'])} skipped"

        md = [
            f"# {title}",
            "",
            f"**Result**: {'PASSED' if not jobs['failed'] else 'FAILED'}",
            f"**Jobs**: {header}",
            "",
            "| Job | Status | Duration |",
            "|-----|--------|----------|",
        ]
        for job in all_jobs:
            duration = f"{job.duration_s:.0f}s" if job.duration_s else "-"
            md.append(f"| {job.name} | {job_status(job)} | {duration} |")
        with open(gh_path, "a") as f:
            f.write("\n".join(md))
