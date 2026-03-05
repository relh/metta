from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from devops.runners.acceptance_criterion import AcceptanceCriterion
from devops.runners.metta_constants import METTA_WANDB_ENTITY, METTA_WANDB_PROJECT


class JobStatus(StrEnum):
    NOT_STARTED = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobHandle(Protocol):
    """Handle for a running job."""

    @property
    def futures(self) -> list[Future]: ...


@dataclass(frozen=True)
class JobResult:
    """Result from job execution."""

    job: Job
    status: JobStatus
    exit_code: int
    error: str | None = None


class Job(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    cmd: list[str]
    executor: JobExecutor
    timeout_s: int = 3600
    remote_id: str | None = None
    remote_gpus: int | None = None  # Only used for SkyPilot jobs
    remote_nodes: int | None = None  # Only used for SkyPilot jobs
    dependencies: list[str] = Field(default_factory=list)
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)
    wandb_run_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    status: JobStatus = JobStatus.NOT_STARTED
    exit_code: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_s: float | None = None
    logs_path: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    acceptance_passed: bool | None = None
    criterion_results: dict[str, bool] = Field(default_factory=dict)
    acceptance_failures: list[str] = Field(default_factory=list)
    error: str | None = None

    @property
    def is_remote(self) -> bool:
        return self.executor.is_remote

    @property
    def wandb_url(self) -> str | None:
        if not self.wandb_run_name:
            return None
        return f"https://wandb.ai/{METTA_WANDB_ENTITY}/{METTA_WANDB_PROJECT}/runs/{self.wandb_run_name}"


class ExecutorType(StrEnum):
    LOCAL = "local"
    SKYPILOT = "skypilot"
    COGAMES = "cogames"


@runtime_checkable
class JobExecutor(Protocol):
    """Interface for job execution backends."""

    ex_type: ExecutorType
    is_remote: bool

    def poll(self, running_jobs: list[Job], remote_not_found_deadline: dict[str, datetime]) -> list[JobResult] | None:
        """
        Jobs of async nature (e.g. SkyPilot jobs) can be intermittently polled to get a status.
        Only used for remote jobs.

        Args:
            running_jobs: expects a filtered list of jobs that are running and only of a single ExecutorType
            remote_not_found_deadline: when to timeout when a status cannot be obtained remotely a dict of
                job.name -> deadline datetime

        Returns:
            A list of results for each Job. Omitting statuses for jobs that need to be polled again.
        """
        ...

    def launch(self, job: Job, log_path: Path, executor: ThreadPoolExecutor) -> JobHandle:
        """Launch a job and return a handle for tracking."""
        ...

    def cancel(self, job: Job) -> None:
        """Cancel a running job."""
        ...

    def on_future_done(self, job: Job, future: Future[Any]) -> JobResult | None:
        """
        Executor-specific handler of a Job's Future.

        Executors are responsible for handling the .result() of the Future.
        A 'None' return value indicates that the Job is remote and asynchronous in nature and
        that the result should be polled on the 'poll' method of the executor. It is expected
        that this call sets job.remote_id for remote jobs to initiate polls.

        Args:
            job: The Job for which the Future should be resolved
            future: The unresolved Future, .result() must be handled within this function

        Returns:
            Union of JobResult or None. Where None is only valid for non-LOCAL ExecutorTypes
            and indicates that `.poll()` should be called.

        """
        ...
