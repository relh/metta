from typing import TypedDict

from devops.runners.core import Runner
from devops.runners.job import Job


class CategorizedJobs(TypedDict):
    failed: list[Job]
    passed: list[Job]
    skipped: list[Job]


def job_failed(job: Job) -> bool:
    return job.status.value == "failed" or (job.status.value == "succeeded" and job.acceptance_passed is False)


def job_status(job: Job) -> str:
    if job_failed(job):
        return "FAILED"
    return job.status.value.upper()


def build_categorized_jobs(runner: Runner) -> CategorizedJobs:
    runner_jobs = runner.jobs.values()

    return {
        "failed": [j for j in runner_jobs if job_failed(j)],
        "passed": [j for j in runner_jobs if j.status.value == "succeeded" and not job_failed(j)],
        "skipped": [j for j in runner_jobs if j.status.value == "skipped"],
    }
