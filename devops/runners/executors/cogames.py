from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from cogames.main import TournamentServerClient
from devops.runners.job import ExecutorType, Job, JobExecutor, JobHandle, JobResult, JobStatus


@dataclass(frozen=True)
class CogamesHandle(JobHandle):
    future: Future[str | None]

    @property
    def futures(self) -> list[Future]:
        return [self.future]


class CogamesCliExecutor(JobExecutor):
    """Executor for remote cogames CLI submit and polling for matches via SDK."""

    ex_type = ExecutorType.COGAMES
    is_remote = True

    def __init__(self, token: str, login_server: str, server_url: str):
        self.client = TournamentServerClient(
            login_server=login_server,
            server_url=server_url,
            token=token,
        )

    def launch(self, job: Job, log_path: Path, executor):
        future = executor.submit(self._run_cogames_cmd, job, log_path)
        return CogamesHandle(future=future)

    def _run_cogames_cmd(self, job: Job, log_path: Path) -> str | None:
        proc = subprocess.Popen(
            job.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=log_path.parent,
        )

        output_lines: list[str] = []
        with open(log_path, "w") as log_file:
            last_flush = time.monotonic()
            assert proc.stdout is not None
            for line in proc.stdout:
                log_file.write(line)
                output_lines.append(line)
                now = time.monotonic()
                if now - last_flush >= 0.5:
                    log_file.flush()
                    last_flush = now

        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"_run_cogames_cmd unexpected exit code: {ret}; see {log_path}")

        output = "".join(output_lines)
        data = json.loads(output)
        if isinstance(data, list):
            data = data[0]
        job_id = str(UUID(data["id"]))

        with open(log_path, "a") as log_file:
            log_file.write(f"Obtained policy_version_id='{job_id}', starting poll.\n")
            log_file.flush()

        return job_id

    def poll(self, running_jobs: list[Job], remote_not_found_deadline: dict[str, datetime]) -> list[JobResult] | None:
        now = datetime.now()
        job_results: list[JobResult] = []

        for job in running_jobs:
            if not job.remote_id:
                continue

            deadline = remote_not_found_deadline.get(job.name)
            try:
                matches = self.client.get_season_matches(
                    "test-season", include_hidden_seasons=True, policy_version_ids=[UUID(job.remote_id)]
                )

                if not matches:
                    if deadline and now > deadline:
                        job_results.append(
                            JobResult(
                                job=job,
                                status=JobStatus.FAILED,
                                exit_code=1,
                                error="Job not found before deadline",
                            )
                        )

                    continue

                expected_status = job.metadata["expected_subjob_status"]

                bad_status = "failed" if expected_status == "completed" else "completed"
                all_expected = all(j.status == expected_status for j in matches)
                any_bad = any(j.status == bad_status for j in matches)

                if all_expected:
                    job_results.append(JobResult(job=job, status=JobStatus.SUCCEEDED, exit_code=0))
                elif any_bad:
                    job_results.append(
                        JobResult(
                            job=job,
                            status=JobStatus.FAILED,
                            exit_code=1,
                            error=f"Expected all subjobs '{expected_status}' for {job.name}, but found '{bad_status}'.",
                        )
                    )
                elif job.started_at and now >= job.started_at + timedelta(seconds=job.timeout_s):
                    job_results.append(
                        JobResult(
                            job=job,
                            status=JobStatus.FAILED,
                            exit_code=1,
                            error=f"Did not find expected status '{expected_status}' for {job.name} before timeout.",
                        )
                    )

            except Exception as e:
                print(f"[{job.name}] Poll error: {e}", flush=True)

                if deadline and now >= deadline:
                    job_results.append(
                        JobResult(
                            job=job,
                            status=JobStatus.FAILED,
                            exit_code=1,
                            error="Job not found before deadline",
                        )
                    )
                # Continue polling

        return job_results if job_results else None

    def cancel(self, job: Job) -> None:
        """No job cancellation supported for cogames"""
        pass

    def on_future_done(self, job: Job, future: Future[str | None]) -> JobResult | None:
        try:
            result = future.result()
        except Exception as e:
            return JobResult(job=job, status=JobStatus.FAILED, exit_code=1, error=str(e))

        if result is None:
            return JobResult(
                job=job,
                status=JobStatus.FAILED,
                exit_code=1,
                error="Submit succeeded but no job_id was found",
            )

        job.remote_id = result
        return None
