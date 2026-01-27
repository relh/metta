import logging
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

import boto3
from botocore.config import Config
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from metta.app_backend.auth import CheckUser
from metta.app_backend.database import db_session
from metta.app_backend.job_runner.dispatcher import dispatch_job
from metta.app_backend.models.job_request import JobRequest, JobRequestCreate, JobRequestUpdate, JobStatus, JobType
from metta.app_backend.otel.metrics import get_job_metrics
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.tournament.settings import JOB_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

MAX_OUTSTANDING_JOBS = 200

DEBUG_S3_BUCKET = "observatory-private"
DEBUG_S3_PREFIX = "replays/tournament"


def _fixup_episode_job(job: JobRequest) -> None:
    if job.job.get("debug_uri") is None:
        s3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version="s3v4"))
        job.job = {
            **job.job,
            "debug_uri": s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": DEBUG_S3_BUCKET,
                    "Key": f"{DEBUG_S3_PREFIX}/{job.id}.debug.zip",
                    "ContentType": "application/zip",
                },
                ExpiresIn=JOB_TIMEOUT_SECONDS + 60 * 60,
            ),
        }


VALID_TRANSITIONS = {
    JobStatus.pending: {JobStatus.dispatched},
    JobStatus.dispatched: {
        JobStatus.running,
        JobStatus.failed,
        JobStatus.completed,  # allowed for watcher reconciliation
    },
    JobStatus.running: {JobStatus.completed, JobStatus.failed},
}


def create_job_router() -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])

    @router.post("/batch")
    @timed_http_handler
    async def create_jobs_batch(jobs: list[JobRequestCreate], user: CheckUser) -> list[UUID]:
        if not jobs:
            return []

        # Backpressure: reject if too many outstanding jobs
        async with db_session() as session:
            outstanding_statuses = [JobStatus.pending, JobStatus.dispatched, JobStatus.running]
            count_result = await session.execute(
                select(func.count()).select_from(JobRequest).where(col(JobRequest.status).in_(outstanding_statuses))
            )
            outstanding_count = count_result.scalar() or 0
            if outstanding_count + len(jobs) > MAX_OUTSTANDING_JOBS:
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many outstanding jobs ({outstanding_count}). Max allowed: {MAX_OUTSTANDING_JOBS}",
                )

        # Create all jobs in db as pending
        db_jobs: list[JobRequest] = []
        async with db_session() as session:
            for job_create in jobs:
                db_job = JobRequest(**job_create.model_dump(), user_id=user.id, status=JobStatus.pending)
                if db_job.job_type == JobType.episode:
                    _fixup_episode_job(db_job)
                session.add(db_job)
                db_jobs.append(db_job)
            await session.commit()
            # Capture IDs before session closes
            job_data = [
                (j.id, j, job_create.use_tournament_account) for j, job_create in zip(db_jobs, jobs, strict=True)
            ]

        class _DispatchResult(BaseModel):
            k8s_job_name: Optional[str] = None
            error: Optional[str] = None
            time: datetime

        # Dispatch each job (outside DB session)
        dispatch_results: dict[UUID, _DispatchResult] = {}
        for job_id, db_job, use_tournament_account in job_data:
            try:
                dispatch_results[job_id] = _DispatchResult(
                    k8s_job_name=dispatch_job(db_job, use_tournament_account=use_tournament_account),
                    time=datetime.now(UTC),
                )
            except Exception as e:
                logger.error(f"Failed to dispatch job {job_id}: {e}", exc_info=True)
                dispatch_results[job_id] = _DispatchResult(error=str(e), time=datetime.now(UTC))

        metrics = get_job_metrics()

        # Update DB with dispatch results
        async with db_session() as session:
            query = await session.execute(select(JobRequest).where(col(JobRequest.id).in_(dispatch_results.keys())))
            job_requests = list(query.scalars().all())
            for job_request in job_requests:
                result = dispatch_results.get(job_request.id)
                if not result:
                    logger.error(f"Job {job_request.id} not found in dispatch results")
                    continue
                if result.k8s_job_name:
                    job_request.status = JobStatus.dispatched
                    job_request.worker = result.k8s_job_name
                    job_request.dispatched_at = result.time
                    metrics.record_transition(
                        JobStatus.pending,
                        JobStatus.dispatched,
                        job_request,
                        result.time,
                        None,
                    )
                else:
                    job_request.status = JobStatus.failed
                    job_request.error = result.error
                    job_request.error_type = "unknown"  # Dispatch failures are generic
                    metrics.record_transition(
                        JobStatus.pending,
                        JobStatus.failed,
                        job_request,
                        result.time,
                        "unknown",
                    )
            await session.commit()
            await metrics.update_running_counts(session, {job.job_type for job in job_requests})
            return [job_request.id for job_request in job_requests]

    @router.get("")
    @timed_http_handler
    async def list_jobs(
        _user: CheckUser,
        job_type: JobType | None = Query(default=None),
        statuses: list[JobStatus] | None = Query(default=None),
        job_id: UUID | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> list[JobRequest]:
        async with db_session() as session:
            query = select(JobRequest).order_by(col(JobRequest.created_at).desc()).offset(offset).limit(limit)
            if job_id:
                query = query.where(JobRequest.id == job_id)
            if statuses:
                query = query.where(col(JobRequest.status).in_(statuses))
            if job_type:
                query = query.where(col(JobRequest.job_type) == job_type)
            result = await session.execute(query)
            return list(result.scalars().all())

    @router.get("/{job_id}")
    @timed_http_handler
    async def get_job(job_id: UUID, _user: CheckUser) -> JobRequest:
        async with db_session() as session:
            result = await session.execute(select(JobRequest).where(JobRequest.id == job_id))
            row = result.scalar_one_or_none()
            if not row:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            return row

    @router.post("/{job_id}")
    @timed_http_handler
    async def update_job(job_id: UUID, request: JobRequestUpdate, _user: CheckUser) -> JobRequest:
        async with db_session() as session:
            result = await session.execute(select(JobRequest).where(JobRequest.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

            transition_time: Optional[datetime] = None
            previous_status: Optional[JobStatus] = None
            if request.status is not None:
                transition_time = datetime.now(UTC)
                previous_status = job.status
                allowed = VALID_TRANSITIONS.get(job.status, set())
                if request.status not in allowed:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cannot transition from {job.status} to {request.status}",
                    )

                job.status = request.status

                if request.status == JobStatus.running:
                    job.running_at = transition_time
                    if request.worker:
                        job.worker = request.worker
                if request.status in (JobStatus.completed, JobStatus.failed):
                    job.completed_at = transition_time

            if request.error is not None:
                job.error = request.error

            if request.error_type is not None:
                job.error_type = request.error_type

            if request.result is not None:
                job.result = request.result
                if job.completed_at is None:
                    job.completed_at = transition_time or datetime.now(UTC)

            # Record metrics BEFORE commit to ensure they're captured even if subsequent operations fail
            if request.status is not None and previous_status is not None and transition_time is not None:
                metrics = get_job_metrics()
                metrics.record_transition(previous_status, request.status, job, transition_time, job.error_type)

            await session.commit()
            await session.refresh(job)

            # Update running counts after commit (gauge based on current DB state)
            if request.status is not None:
                metrics = get_job_metrics()
                await metrics.update_running_counts(session, {job.job_type})
            return job

    return router
