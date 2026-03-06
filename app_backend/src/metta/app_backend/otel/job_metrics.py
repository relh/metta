"""Job-specific OTel metrics (state transitions, stage durations, running counts)."""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Optional

from opentelemetry import metrics as otel_metrics
from opentelemetry.metrics import CallbackOptions, Observation
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlmodel import col, select

from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.otel.metrics import init_meter_provider


def compute_job_cost(
    start_at: datetime | None,
    end_at: datetime,
    cost_per_pod_hour: float,
) -> float | None:
    """Compute job cost in USD from duration and hourly rate.

    start_at should be dispatched_at (includes pod startup) or running_at.
    Returns None if cost cannot be determined (missing start_at, zero rate,
    or non-positive duration from clock skew).
    """
    if cost_per_pod_hour <= 0 or start_at is None:
        return None
    s = start_at.replace(tzinfo=UTC) if start_at.tzinfo is None else start_at
    e = end_at.replace(tzinfo=UTC) if end_at.tzinfo is None else end_at
    duration_hours = (e - s).total_seconds() / 3600
    if duration_hours <= 0:
        return None
    return duration_hours * cost_per_pod_hour


class JobMetrics:
    def __init__(self) -> None:
        init_meter_provider()
        meter = otel_metrics.get_meter(__name__)
        self._state_transition_counter = meter.create_counter(
            "job.state_transition",
            description="Job status transitions",
            unit="1",
        )
        self._stage_duration_histogram = meter.create_histogram(
            "job.stage_duration",
            description="Time spent in job lifecycle stages",
            unit="s",
        )
        self._cost_counter = meter.create_counter(
            "job.cost",
            description="Cumulative job compute cost",
            unit="USD",
        )
        self._episode_length_histogram = meter.create_histogram(
            "episode.length",
            description="Number of environment steps in a completed episode",
            unit="1",
        )
        self._event_processing_lag_histogram = meter.create_histogram(
            "job.event_processing_lag",
            description="Time between k8s event insertion and processing",
            unit="s",
        )
        self._running_counts: dict[str, int] = {}
        self._outstanding_counts: dict[tuple[str, str], int] = {}
        meter.create_observable_gauge(
            "job.running_count",
            callbacks=[self._observe_running_count],
            description="Current number of running jobs",
            unit="1",
        )
        meter.create_observable_gauge(
            "job.outstanding_count",
            callbacks=[self._observe_outstanding_count],
            description="Jobs by status (pending/dispatched/running)",
            unit="1",
        )

    def _observe_running_count(self, options: CallbackOptions) -> Iterable[Observation]:
        del options
        snapshot = dict(self._running_counts)
        return [Observation(count, {"job_type": job_type}) for job_type, count in snapshot.items()]

    def _observe_outstanding_count(self, options: CallbackOptions) -> Iterable[Observation]:
        del options
        snapshot = dict(self._outstanding_counts)
        return [Observation(count, {"job_type": jt, "status": st}) for (jt, st), count in snapshot.items()]

    def record_event_processing_lag(self, created_at: datetime, processed_at: datetime, job_type: str = "") -> None:
        c = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
        p = processed_at.replace(tzinfo=UTC) if processed_at.tzinfo is None else processed_at
        lag = (p - c).total_seconds()
        if lag >= 0:
            attrs: dict[str, str] = {}
            if job_type:
                attrs["job_type"] = job_type
            self._event_processing_lag_histogram.record(lag, attributes=attrs)

    def record_episode_length(self, steps: int, job_type: str) -> None:
        self._episode_length_histogram.record(
            steps,
            attributes={"job_type": job_type},
        )

    def _record_stage_duration(
        self,
        stage: str,
        start_at: Optional[datetime],
        end_at: datetime,
        job_type: JobType,
        outcome: str = "",
    ) -> None:
        if start_at is None:
            return
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=UTC)
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=UTC)
        duration_seconds = (end_at - start_at).total_seconds()
        if duration_seconds < 0:
            return
        attrs: dict[str, str] = {"stage": stage, "job_type": job_type.value}
        if outcome:
            attrs["outcome"] = outcome
        self._stage_duration_histogram.record(duration_seconds, attributes=attrs)

    def record_transition(
        self,
        from_status: JobStatus,
        to_status: JobStatus,
        job: JobRequest,
        transition_time: datetime,
        error_type: Optional[str],
        cost_usd: float | None = None,
    ) -> None:
        self._state_transition_counter.add(
            1,
            attributes={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "job_type": job.job_type.value,
                "error_type": error_type or "none",
            },
        )
        outcome = to_status.value if to_status in (JobStatus.completed, JobStatus.failed) else ""
        if from_status == JobStatus.pending:
            self._record_stage_duration("pending", job.created_at, transition_time, job.job_type)
        elif from_status == JobStatus.dispatched:
            self._record_stage_duration("dispatched", job.dispatched_at, transition_time, job.job_type, outcome=outcome)
            if cost_usd is not None and cost_usd > 0:
                self._cost_counter.add(cost_usd, attributes={"job_type": job.job_type.value, "outcome": outcome})
        elif from_status == JobStatus.running:
            self._record_stage_duration("running", job.running_at, transition_time, job.job_type, outcome=outcome)
            if cost_usd is not None and cost_usd > 0:
                self._cost_counter.add(cost_usd, attributes={"job_type": job.job_type.value, "outcome": outcome})

    def _apply_counts(self, result: Sequence[Any], job_types: set[JobType]) -> None:
        outstanding_statuses = [JobStatus.pending, JobStatus.dispatched, JobStatus.running]
        counts_by_type_status: dict[tuple[JobType, JobStatus], int] = {}
        for job_type, status, count in result:
            counts_by_type_status[(job_type, status)] = count

        for job_type in job_types:
            for status in outstanding_statuses:
                key = (job_type.value, status.value)
                self._outstanding_counts[key] = counts_by_type_status.get((job_type, status), 0)
            self._running_counts[job_type.value] = counts_by_type_status.get((job_type, JobStatus.running), 0)

    def _counts_query(self, job_types: set[JobType]):
        outstanding_statuses = [JobStatus.pending, JobStatus.dispatched, JobStatus.running]
        return (
            select(JobRequest.job_type, JobRequest.status, func.count())
            .where(col(JobRequest.status).in_(outstanding_statuses))
            .where(col(JobRequest.job_type).in_(job_types))
            .group_by(JobRequest.job_type, JobRequest.status)
        )

    def update_running_counts(self, session: Session, job_types: set[JobType]) -> None:
        if not job_types:
            return
        result = session.execute(self._counts_query(job_types))
        self._apply_counts(result.all(), job_types)


@lru_cache
def get_job_metrics() -> JobMetrics:
    return JobMetrics()
