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
        error: str | None = None
        if exit_code == 124:
            error = f"Timeout after {job.timeout_s}s"
        elif exit_code != 0:
            error = self._tail_log(job)
        return JobResult(
            job=job,
            status=JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED,
            exit_code=exit_code,
            error=error,
        )

    @staticmethod
    def _tail_log(job: Job, max_bytes: int = 300) -> str | None:
        """Read the tail of the job log to extract the error message."""
        if not job.logs_path:
            return None
        log_path = Path(job.logs_path)
        if not log_path.is_file():
            return None
        size = log_path.stat().st_size
        if size == 0:
            return None
        with open(log_path, "rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, 2)
            tail = f.read().decode("utf-8", errors="replace").strip()
        return tail or None

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
