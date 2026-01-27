import asyncio
import logging
from datetime import UTC, datetime
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

import boto3
from botocore.config import Config
from fastapi import APIRouter, HTTPException, Query
from metta_alo.policy import parse_policy_identifier
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from metta.app_backend.auth import CheckUser
from metta.app_backend.database import db_session
from metta.app_backend.job_runner.dispatcher import dispatch_job
from metta.app_backend.models.job_request import (
    JobPolicyVersion,
    JobRequest,
    JobRequestCreate,
    JobRequestUpdate,
    JobStatus,
    JobType,
)
from metta.app_backend.models.policies import PolicyVersion
from metta.app_backend.otel.metrics import get_job_metrics
from metta.app_backend.queries import policy_queries
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


async def _resolve_policy_uris(policy_uris: list[str]) -> list[tuple[int, UUID, str]]:
    resolved: list[tuple[int, UUID, str]] = []
    for i, uri in enumerate(policy_uris):
        if not uri.startswith("metta://"):
            raise ValueError(f"Only metta:// policy URIs are supported, got: {uri}")
        pv = await _resolve_metta_policy_uri(uri)
        if not pv.s3_path:
            raise ValueError(f"Policy version {pv.id} has no s3_path")
        s3_key = urlparse(pv.s3_path).path.lstrip("/")
        resolved.append((i, pv.id, s3_key))
    return resolved


async def _resolve_metta_policy_uri(uri: str) -> PolicyVersion:
    path = uri[len("metta://") :]
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != "policy":
        raise ValueError(f"Unsupported metta:// URI format: {uri}")

    identifier = parts[1]
    try:
        pv_id = UUID(identifier)
    except ValueError:
        pv_id = None

    if pv_id is not None:
        pv = await policy_queries.get_policy_version_with_name(pv_id)
        if pv is None:
            raise ValueError(f"Policy version {identifier} not found")
        return pv

    name, version = parse_policy_identifier(identifier)
    versions, _ = await policy_queries.get_policy_versions(name_exact=name, version=version, limit=1)
    if not versions:
        version_str = f":v{version}" if version is not None else ""
        raise ValueError(f"No policy found with name '{name}{version_str}'")
    return versions[0]


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

        # Resolve metta:// policy URIs -> (position, policy_version_id, s3_key)
        job_resolved: list[list[tuple[int, UUID, str]]] = []
        for job_create in jobs:
            policy_uris = job_create.job.get("policy_uris", [])
            job_resolved.append(await _resolve_policy_uris(policy_uris) if policy_uris else [])

        # Create all jobs in db as pending
        db_jobs: list[JobRequest] = []
        async with db_session() as session:
            for job_create in jobs:
                db_job = JobRequest(**job_create.model_dump(), user_id=user.id, status=JobStatus.pending)
                if db_job.job_type == JobType.episode:
                    _fixup_episode_job(db_job)
                session.add(db_job)
                db_jobs.append(db_job)
            await session.flush()

            # Create junction table entries
            for db_job, resolved in zip(db_jobs, job_resolved, strict=True):
                for position, pv_id, _ in resolved:
                    session.add(JobPolicyVersion(job_id=db_job.id, position=position, policy_version_id=pv_id))

            await session.commit()
            # Capture IDs before session closes
            job_data = [
                (j.id, j, job_create.use_tournament_account, {pos: key for pos, _, key in resolved})
                for j, job_create, resolved in zip(db_jobs, jobs, job_resolved, strict=True)
            ]

        class _DispatchResult(BaseModel):
            k8s_job_name: Optional[str] = None
            error: Optional[str] = None
            time: datetime

        # Dispatch each job (outside DB session)
        # Run in a thread so sync I/O (boto3, httpx) doesn't block the event loop
        dispatch_results: dict[UUID, _DispatchResult] = {}
        for job_id, db_job, use_tournament_account, s3_keys in job_data:
            try:
                k8s_job_name = await asyncio.to_thread(
                    dispatch_job, db_job, use_tournament_account=use_tournament_account, policy_s3_keys=s3_keys
                )
                dispatch_results[job_id] = _DispatchResult(
                    k8s_job_name=k8s_job_name,
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
        policy_version_id: UUID | None = Query(default=None),
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
            if policy_version_id:
                query = query.join(JobPolicyVersion).where(JobPolicyVersion.policy_version_id == policy_version_id)
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
