"""Remote SkyPilot job executor"""

from __future__ import annotations

import subprocess
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sky
import sky.jobs.client.sdk as sky_jobs_sdk

from devops.runners.job import ExecutorType, Job, JobExecutor, JobHandle, JobResult, JobStatus


@dataclass(frozen=True)
class SkypilotHandle(JobHandle):
    future: Future[str | None]

    @property
    def futures(self) -> list[Future]:
        return [self.future]


class SkypilotExecutor(JobExecutor):
    """Executor for remote Skypilot jobs"""

    ex_type = ExecutorType.SKYPILOT
    is_remote = True

    def launch(self, job: Job, log_path: Path, executor: ThreadPoolExecutor) -> SkypilotHandle:
        """Launch a remote SkyPilot job"""
        future = executor.submit(self._run_skypilot_cmd, job, log_path)
        return SkypilotHandle(future=future)

    def poll(self, running_jobs: list[Job], remote_not_found_deadline: dict[str, datetime]) -> list[JobResult] | None:
        """
        Poll SkyPilot job statuses, create a JobResult list if some status is returned
        otherwise let it poll in a later attempt by returning None.
        """
        now = datetime.now()
        job_ids = [int(j.remote_id) for j in running_jobs if j.remote_id]

        if not job_ids:
            return None

        request_id = sky_jobs_sdk.queue(refresh=False, job_ids=job_ids)
        queue_data = sky.get(request_id)

        if not isinstance(queue_data, list):
            raise TypeError(f"Expect Skypilot queue data to be a list, got {type(queue_data).__name__}")

        status_by_id = {
            str(item.get("job_id") if isinstance(item, dict) else getattr(item, "job_id", None)): item
            for item in queue_data
        }

        job_results: list[JobResult] = []

        for job in running_jobs:
            if not job.remote_id:
                continue

            sky_job = status_by_id.get(job.remote_id)
            deadline = remote_not_found_deadline.get(job.name)

            if not sky_job:
                if deadline and now >= deadline:
                    job_results.append(
                        JobResult(
                            job=job,
                            status=JobStatus.FAILED,
                            exit_code=1,
                            error="Job not found in SkyPilot queue before deadline",
                        )
                    )
                continue

            status = sky_job.get("status") if isinstance(sky_job, dict) else getattr(sky_job, "status", None)
            sky_status = str(status or "").upper()

            if "SUCCEEDED" in sky_status:
                job_results.append(JobResult(job=job, status=JobStatus.SUCCEEDED, exit_code=0))
            elif any(s in sky_status for s in ("FAILED", "CANCELLED")):
                job_results.append(
                    JobResult(job=job, status=JobStatus.FAILED, exit_code=1, error=f"SkyPilot status: {sky_status}")
                )
        return job_results

    def cancel(self, job: Job) -> None:
        """Ensure SkyPilot jobs get cancelled if e.g. a time limit is exceeded"""
        if job.remote_id is None:
            # Job has not launched yet, nothing to cancel
            return

        subprocess.run(["sky", "jobs", "cancel", "-y", job.remote_id], capture_output=True)

    def on_future_done(self, job: Job, future: Future[str | None]) -> JobResult | None:
        """Handles the result of the SkyPilot thread Future"""
        try:
            result = future.result()
        except Exception as e:
            return JobResult(job=job, status=JobStatus.FAILED, exit_code=1, error=str(e))

        if result is None:
            return JobResult(
                job=job,
                status=JobStatus.FAILED,
                exit_code=1,
                error="SkyPilot launch succeeded, but no job_id was returned",
            )

        job.remote_id = result
        return None

    def _run_skypilot_cmd(self, job: Job, log_path: Path) -> str | None:
        proc = subprocess.Popen(
            job.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        job_id: str | None = None
        with open(log_path, "w") as log_file:
            assert proc.stdout is not None
            last_flush = time.monotonic()
            for line in proc.stdout:
                log_file.write(line)
                now = time.monotonic()
                if now - last_flush >= 0.5:
                    log_file.flush()
                    last_flush = now
                if "Job ID:" in line:
                    job_id = line.split(":")[-1].strip()
            log_file.flush()

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"remote job exited with code {proc.returncode}")
        return job_id
