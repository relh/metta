"""Local subprocess-based job executor."""

from __future__ import annotations

import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from devops.runners.job import ExecutorType, Job, JobExecutor, JobHandle, JobResult, JobStatus


@dataclass(frozen=True)
class LocalHandle(JobHandle):
    """Handle for local subprocess jobs."""

    future: Future[int]

    @property
    def futures(self) -> list[Future]:
        return [self.future]


class LocalExecutor(JobExecutor):
    """Executor for local subprocess jobs."""

    ex_type = ExecutorType.LOCAL
    is_remote = False

    def launch(self, job: Job, log_path: Path, executor: ThreadPoolExecutor) -> LocalHandle:
        """Launch a local subprocess job."""
        future = executor.submit(self._run_local_cmd, job, log_path, job.timeout_s)
        return LocalHandle(future=future)

    def poll(self, running_jobs: list[Job], remote_not_found_deadline: dict[str, datetime]) -> list[JobResult] | None:
        """Local jobs are tracked by futures, so polling is not needed."""
        pass

    def cancel(self, job: Job) -> None:
        """Cancel local subprocess (not implemented - relies on timeout)."""
        pass

    def on_future_done(self, job: Job, future: Future[int]) -> JobResult | None:
        """Obtain the process' exit code and create the JobResult from it"""
        try:
            result = future.result()
        except Exception as e:
            return JobResult(job=job, status=JobStatus.FAILED, exit_code=1, error=str(e))

        exit_code = int(result)
        return JobResult(
            job=job,
            status=JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED,
            exit_code=exit_code,
            error=f"Timeout after {job.timeout_s}s" if exit_code == 124 else None,
        )

    def _run_local_cmd(self, job: Job, log_path: Path, timeout_s: int) -> int:
        """Run a local command and return exit code."""
        with open(log_path, "w") as log_file:
            try:
                proc = subprocess.run(
                    job.cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout_s,
                    check=False,
                )
                return int(proc.returncode)
            except subprocess.TimeoutExpired:
                return 124
