from collections.abc import Iterable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Optional

from opentelemetry import metrics as otel_metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from pydantic_settings import BaseSettings
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType

METRICS_SERVICE_NAME = "observatory-backend"


class MetricsSettings(BaseSettings):
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Optional[str] = None


@lru_cache
def get_metrics_settings() -> MetricsSettings:
    return MetricsSettings()


def _metrics_enabled(settings: MetricsSettings) -> bool:
    return bool(settings.OTEL_EXPORTER_OTLP_METRICS_ENDPOINT)


class JobMetrics:
    def __init__(self) -> None:
        settings = get_metrics_settings()
        if _metrics_enabled(settings):
            resource = Resource.create({"service.name": METRICS_SERVICE_NAME})
            reader = PeriodicExportingMetricReader(OTLPMetricExporter())
            provider = MeterProvider(resource=resource, metric_readers=[reader])
            otel_metrics.set_meter_provider(provider)

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

    def _record_stage_duration(
        self,
        stage: str,
        start_at: Optional[datetime],
        end_at: datetime,
        job_type: JobType,
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
        self._stage_duration_histogram.record(
            duration_seconds,
            attributes={"stage": stage, "job_type": job_type.value},
        )

    def record_transition(
        self,
        from_status: JobStatus,
        to_status: JobStatus,
        job: JobRequest,
        transition_time: datetime,
        error_type: Optional[str],
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
        if from_status == JobStatus.pending:
            self._record_stage_duration("pending", job.created_at, transition_time, job.job_type)
        elif from_status == JobStatus.dispatched:
            # Reconciliation can mark dispatched -> completed/failed without a running phase.
            self._record_stage_duration("dispatched", job.dispatched_at, transition_time, job.job_type)
        elif from_status == JobStatus.running:
            self._record_stage_duration("running", job.running_at, transition_time, job.job_type)

    async def update_running_counts(self, session: AsyncSession, job_types: set[JobType]) -> None:
        if not job_types:
            return

        outstanding_statuses = [JobStatus.pending, JobStatus.dispatched, JobStatus.running]
        result = await session.execute(
            select(JobRequest.job_type, JobRequest.status, func.count())
            .where(col(JobRequest.status).in_(outstanding_statuses))
            .where(col(JobRequest.job_type).in_(job_types))
            .group_by(JobRequest.job_type, JobRequest.status)
        )

        counts_by_type_status: dict[tuple[JobType, JobStatus], int] = {}
        for job_type, status, count in result.all():
            counts_by_type_status[(job_type, status)] = count

        for job_type in job_types:
            for status in outstanding_statuses:
                key = (job_type.value, status.value)
                self._outstanding_counts[key] = counts_by_type_status.get((job_type, status), 0)
            self._running_counts[job_type.value] = counts_by_type_status.get((job_type, JobStatus.running), 0)


@lru_cache
def get_job_metrics() -> JobMetrics:
    return JobMetrics()
