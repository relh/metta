# pyright: reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnusedVariable=false, reportUnusedFunction=false
# SQLModel type stubs cause false positives; route handlers appear "unused" inside factory function

import asyncio
import io
import logging
import zipfile
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

import boto3
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from metta.app_backend.auth import SoftmaxUser
from metta.app_backend.database import db_session
from metta.app_backend.ec2_pricing import get_instance_hourly_cost
from metta.app_backend.job_runner.config import get_dispatch_config
from metta.app_backend.job_runner.dispatcher import dispatch_job
from metta.app_backend.job_runner.job_artifacts import (
    job_debug_key,
    job_logs_key,
    job_policy_log_key,
    job_policy_log_prefix,
    job_replay_key,
    job_results_key,
    job_runtime_info_key,
    job_spec_key,
    read_job_artifact,
)
from metta.app_backend.metta_scheme_resolver import parse_policy_identifier
from metta.app_backend.models.episodes import Episode, EpisodeJob, EpisodePolicy, EpisodePolicyMetric
from metta.app_backend.models.job_request import (
    JobPolicyVersion,
    JobRequest,
    JobRequestCreate,
    JobRequestUpdate,
    JobStatus,
    JobType,
)
from metta.app_backend.models.policies import PolicyVersion
from metta.app_backend.models.tournament import Match, Pool
from metta.app_backend.otel.job_metrics import get_job_metrics
from metta.app_backend.queries import policy_queries
from metta.app_backend.queries.episode_stats import PolicyVersionSummary, compute_episode_stats
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.user_data import Ownable, fill_user_data

logger = logging.getLogger(__name__)

MAX_OUTSTANDING_JOBS = 200


class JobPolicyVersionSummary(BaseModel):
    position: int
    policy: PolicyVersionSummary


class EpisodePolicyStat(BaseModel):
    policy_version_id: UUID
    num_agents: int
    avg_reward: float | None


class JobEpisodeInfo(BaseModel):
    replay_url: str | None = None
    attributes: dict[str, Any] | None = None
    policy_stats: list[EpisodePolicyStat] = []


class JobMatchInfo(BaseModel):
    pool_name: str | None = None
    season_name: str | None = None


class JobRequestResponse(Ownable):
    id: UUID
    job_type: JobType
    job: dict[str, Any]
    status: JobStatus
    created_at: datetime
    dispatched_at: datetime | None
    running_at: datetime | None
    completed_at: datetime | None
    worker: str | None
    result: dict[str, Any] | None
    error: str | None
    error_type: str | None
    policy_versions: list[JobPolicyVersionSummary] = []
    episode: JobEpisodeInfo | None = None
    match: JobMatchInfo | None = None

    @classmethod
    def from_job(
        cls,
        job: JobRequest,
        *,
        episode: "JobEpisodeInfo | None" = None,
        match: "JobMatchInfo | None" = None,
    ) -> "JobRequestResponse":
        pvs = [
            JobPolicyVersionSummary(
                position=jpv.position,
                policy=PolicyVersionSummary.from_model(jpv.policy_version),
            )
            for jpv in job.policy_versions
        ]
        return cls(
            **job.model_dump(exclude={"policy_versions"}),
            policy_versions=sorted(pvs, key=lambda e: e.position),
            episode=episode,
            match=match,
        )


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


class AgentStatsDetail(BaseModel):
    agent_id: int
    reward: float
    metrics: dict[str, float]


class PolicyStatsDetail(BaseModel):
    position: int
    policy_version_id: UUID | None
    policy_name: str | None
    policy_version: int | None
    num_agents: int
    avg_metrics: dict[str, float]
    avg_reward: float
    agents: list[AgentStatsDetail]


class EpisodeStatsResponse(BaseModel):
    game_stats: dict[str, float]
    policy_stats: list[PolicyStatsDetail]
    steps: int | None


def create_job_router() -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])

    @router.post("/batch")
    @timed_http_handler
    async def create_jobs_batch(jobs: list[JobRequestCreate], user: SoftmaxUser) -> list[UUID]:
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
                (j.id, j, {pos: key for pos, _, key in resolved})
                for j, resolved in zip(db_jobs, job_resolved, strict=True)
            ]

        class _DispatchResult(BaseModel):
            k8s_job_name: Optional[str] = None
            error: Optional[str] = None
            time: datetime

        # Dispatch each job (outside DB session)
        # Run in a thread so sync I/O (boto3, httpx) doesn't block the event loop
        dispatch_results: dict[UUID, _DispatchResult] = {}
        for job_id, db_job, s3_keys in job_data:
            try:
                k8s_job_name = await asyncio.to_thread(dispatch_job, db_job, policy_s3_keys=s3_keys)
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
                from_status = job_request.status
                if result.k8s_job_name:
                    job_request.status = JobStatus.dispatched
                    job_request.worker = result.k8s_job_name
                    job_request.dispatched_at = result.time
                else:
                    job_request.status = JobStatus.failed
                    job_request.error = result.error
                    job_request.error_type = "unknown"  # Dispatch failures are generic
            await session.commit()
            metrics.record_transition(
                from_status=from_status,
                to_status=job_request.status,
                job=job_request,
                transition_time=result.time,
                error_type=job_request.error_type,
                cost_per_pod_hour=0.0,
            )
            await metrics.update_running_counts(session, {job.job_type for job in job_requests})
            return [job_request.id for job_request in job_requests]

    @router.get("")
    @timed_http_handler
    async def list_jobs(
        user: SoftmaxUser,
        job_type: JobType | None = Query(default=None),
        statuses: list[JobStatus] | None = Query(default=None),
        job_id: UUID | None = Query(default=None),
        policy_version_id: UUID | None = Query(default=None),
        season_id: UUID | None = Query(default=None),
        pool_id: UUID | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> list[JobRequestResponse]:
        async with db_session() as session:
            id_query = select(JobRequest.id).order_by(col(JobRequest.created_at).desc()).offset(offset).limit(limit)
            if job_id:
                id_query = id_query.where(JobRequest.id == job_id)
            if statuses:
                id_query = id_query.where(col(JobRequest.status).in_(statuses))
            if job_type:
                id_query = id_query.where(col(JobRequest.job_type) == job_type)
            if policy_version_id:
                policy_job_ids = select(JobPolicyVersion.job_id).where(
                    JobPolicyVersion.policy_version_id == policy_version_id
                )
                id_query = id_query.where(col(JobRequest.id).in_(policy_job_ids))
            if season_id or pool_id:
                match_pool_query = select(Match.job_id).join(Pool, Pool.id == Match.pool_id)
                if pool_id:
                    match_pool_query = match_pool_query.where(Pool.id == pool_id)
                if season_id:
                    match_pool_query = match_pool_query.where(Pool.season_id == season_id)
                id_query = id_query.where(col(JobRequest.id).in_(match_pool_query))
            id_result = await session.execute(id_query)
            job_ids = [row[0] for row in id_result.all()]
            if not job_ids:
                return []

            query = (
                select(JobRequest)
                .where(col(JobRequest.id).in_(job_ids))
                .options(
                    selectinload(JobRequest.policy_versions)  # type: ignore[arg-type]
                    .joinedload(JobPolicyVersion.policy_version)  # type: ignore[arg-type]
                    .joinedload(PolicyVersion.policy),  # type: ignore[arg-type]
                    selectinload(JobRequest.episode_jobs).joinedload(EpisodeJob.episode),  # type: ignore[arg-type]  # type: ignore[arg-type]
                    selectinload(JobRequest.matches)  # type: ignore[arg-type]
                    .joinedload(Match.pool)  # type: ignore[arg-type]
                    .joinedload(Pool.season),  # type: ignore[arg-type]
                )
                .order_by(col(JobRequest.created_at).desc())
            )
            jobs = (await session.execute(query)).scalars().unique().all()

            completed_job_ids = [jr.id for jr in jobs if jr.status == JobStatus.completed]
            job_policy_stats: dict[UUID, list[EpisodePolicyStat]] = defaultdict(list)
            if completed_job_ids:
                stats_query = (
                    select(
                        EpisodeJob.job_id,
                        EpisodePolicy.policy_version_id,
                        EpisodePolicy.num_agents,
                        EpisodePolicyMetric.value,
                    )
                    .join(Episode, Episode.id == EpisodeJob.episode_id)
                    .join(EpisodePolicy, EpisodePolicy.episode_id == Episode.id)
                    .join(PolicyVersion, PolicyVersion.id == EpisodePolicy.policy_version_id)
                    .outerjoin(
                        EpisodePolicyMetric,
                        (EpisodePolicyMetric.episode_internal_id == Episode.internal_id)
                        & (EpisodePolicyMetric.pv_internal_id == PolicyVersion.internal_id)
                        & (EpisodePolicyMetric.metric_name == "reward"),
                    )
                    .where(col(EpisodeJob.job_id).in_(completed_job_ids))
                )
                stats_result = await session.execute(stats_query)
                for s_job_id, pv_id, num_agents, reward_value in stats_result.all():
                    avg_reward = reward_value / num_agents if reward_value is not None and num_agents > 0 else None
                    job_policy_stats[s_job_id].append(
                        EpisodePolicyStat(policy_version_id=pv_id, num_agents=num_agents, avg_reward=avg_reward)
                    )

        # Session is closed — any missing selectinload will raise DetachedInstanceError
        responses: list[JobRequestResponse] = []
        for jr in jobs:
            # episode_jobs is many-to-one, but we only show the first episode per job for now
            ep = jr.episode_jobs[0].episode if jr.episode_jobs else None
            episode_info = (
                JobEpisodeInfo(
                    replay_url=ep.replay_url if ep else None,
                    attributes=ep.attributes if ep else None,
                    policy_stats=job_policy_stats.get(jr.id, []),
                )
                if ep is not None or jr.id in job_policy_stats
                else None
            )
            m = jr.matches[0] if jr.matches else None
            match_info = (
                JobMatchInfo(
                    pool_name=m.pool.name if m and m.pool else None,
                    season_name=m.pool.season.name if m and m.pool and m.pool.season else None,
                )
                if m is not None
                else None
            )
            responses.append(JobRequestResponse.from_job(jr, episode=episode_info, match=match_info))
        await fill_user_data(responses, current_user=user)
        return responses

    def _extract_trace(body: bytes) -> bytes:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            names = zf.namelist()
            if "trace.json" in names:
                return zf.open("trace.json").read()
            if "setup_trace.json" in names:
                return zf.open("setup_trace.json").read()
            raise KeyError("No trace files found in debug.zip")

    def _extract_setup_trace(body: bytes) -> bytes:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            return zf.open("setup_trace.json").read()

    ARTIFACT_TYPES: dict[str, tuple[Callable[[UUID], str], str, Callable[[bytes], bytes]]] = {
        "logs": (job_logs_key, "text/plain", lambda b: b),
        "spec": (job_spec_key, "application/json", lambda b: b),
        "results": (job_results_key, "application/json", lambda b: b),
        "runtime_info": (job_runtime_info_key, "application/json", lambda b: b),
        "replay": (job_replay_key, "application/octet-stream", lambda b: b),
        "debug": (job_debug_key, "application/zip", lambda b: b),
        "trace": (job_debug_key, "application/json", _extract_trace),
        "setup_trace": (job_debug_key, "application/json", _extract_setup_trace),
    }

    @router.get("/{job_id}/artifacts/{artifact_type}")
    @timed_http_handler
    async def get_job_artifact(job_id: UUID, artifact_type: str, _user: SoftmaxUser) -> Response:
        if artifact_type not in ARTIFACT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_type}")

        key_fn, media_type, extract = ARTIFACT_TYPES[artifact_type]

        async with db_session() as session:
            result = await session.execute(select(JobRequest).where(JobRequest.id == job_id))
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        content, content_type = await read_job_artifact(job_id, key_fn, media_type, extract, artifact_type)
        return Response(content=content, media_type=content_type)

    @router.get("/{job_id}/episode-stats")
    @timed_http_handler
    async def get_job_episode_stats(job_id: UUID, _user: SoftmaxUser) -> EpisodeStatsResponse:
        async with db_session() as session:
            query = (
                select(JobRequest)
                .options(
                    selectinload(JobRequest.policy_versions)  # type: ignore[arg-type]
                    .joinedload(JobPolicyVersion.policy_version)  # type: ignore[arg-type]
                    .joinedload(PolicyVersion.policy)  # type: ignore[arg-type]
                )
                .where(JobRequest.id == job_id)
            )
            result = await session.execute(query)
            job = result.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            if job.status != JobStatus.completed:
                raise HTTPException(status_code=400, detail="Job is not completed")

            episode_id = job.episode_id_uuid
            if not episode_id:
                raise HTTPException(status_code=400, detail="Job has no episode result")

            episode = await session.get(Episode, episode_id)
            if not episode:
                raise HTTPException(status_code=404, detail="Episode not found")

            assignments: list[int] = job.job.get("assignments", [])
            game_stats, policy_results, steps = compute_episode_stats(episode, assignments, job.policy_versions)

            _sentinel = UUID(int=0)
            policy_stats = [
                PolicyStatsDetail(
                    position=pr.position,
                    policy_version_id=None if pr.policy.id == _sentinel else pr.policy.id,
                    policy_name=pr.policy.name,
                    policy_version=pr.policy.version,
                    num_agents=pr.num_agents,
                    avg_metrics=pr.avg_metrics,
                    avg_reward=pr.avg_reward,
                    agents=[
                        AgentStatsDetail(agent_id=a.agent_id, reward=a.reward, metrics=a.metrics) for a in pr.agents
                    ],
                )
                for pr in policy_results
            ]

            return EpisodeStatsResponse(
                game_stats=game_stats,
                policy_stats=policy_stats,
                steps=steps,
            )

    @router.get("/{job_id}")
    @timed_http_handler
    async def get_job(job_id: UUID, user: SoftmaxUser) -> JobRequestResponse:
        async with db_session() as session:
            query = (
                select(JobRequest)
                .options(
                    selectinload(JobRequest.policy_versions)  # type: ignore[arg-type]
                    .joinedload(JobPolicyVersion.policy_version)  # type: ignore[arg-type]
                    .joinedload(PolicyVersion.policy)  # type: ignore[arg-type]
                )
                .where(JobRequest.id == job_id)
            )
            result = await session.execute(query)
            row = result.scalar_one_or_none()
            if not row:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            response = JobRequestResponse.from_job(row)
            await fill_user_data([response], current_user=user)
            return response

    @router.post("/{job_id}")
    @timed_http_handler
    async def update_job(job_id: UUID, request: JobRequestUpdate, _user: SoftmaxUser) -> JobRequest:
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

            # Record metrics BEFORE commit to ensure they're captured even if subsequent operations fail
            if request.status is not None and previous_status is not None and transition_time is not None:
                metrics = get_job_metrics()
                result_data = job.result or {}
                cost_per_pod_hour = get_instance_hourly_cost(
                    result_data.get("instance_type"),
                    result_data.get("capacity_type"),
                    region=get_dispatch_config().EVAL_CLUSTER_REGION,
                )
                metrics.record_transition(
                    previous_status,
                    request.status,
                    job,
                    transition_time,
                    job.error_type,
                    cost_per_pod_hour=cost_per_pod_hour,
                )

            await session.commit()
            await session.refresh(job)

            # Update running counts after commit (gauge based on current DB state)
            if request.status is not None:
                metrics = get_job_metrics()
                await metrics.update_running_counts(session, {job.job_type})
            return job

    # Policy logs use a separate endpoint from /artifacts because they require an agent_idx
    # parameter. See job_artifacts.py for unification notes.
    @router.get("/{job_id}/policy-logs")
    @timed_http_handler
    async def list_policy_logs(job_id: UUID, _user: SoftmaxUser) -> list[str]:
        """List all policy log files for a job."""
        cfg = get_dispatch_config()
        if not cfg.EVAL_S3_BUCKET:
            raise HTTPException(status_code=501, detail="Storage not configured")

        async with db_session() as session:
            result = await session.execute(select(JobRequest).where(JobRequest.id == job_id))
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        def _list_logs() -> list[str]:
            s3 = boto3.client("s3")
            prefix = job_policy_log_prefix(job_id)
            response = s3.list_objects_v2(Bucket=cfg.EVAL_S3_BUCKET, Prefix=prefix)
            return [obj["Key"].split("/")[-1] for obj in response.get("Contents", [])]

        return await asyncio.to_thread(_list_logs)

    @router.get("/{job_id}/policy-logs/{agent_idx}")
    @timed_http_handler
    async def get_policy_log(job_id: UUID, agent_idx: int, _user: SoftmaxUser) -> Response:
        """Get the combined log for a specific agent by index.

        Returns the log content as plain text.
        """
        content, media_type = await read_job_artifact(
            job_id,
            key_fn=lambda jid: job_policy_log_key(jid, agent_idx),
            media_type="text/plain",
            artifact_label=f"policy log for agent {agent_idx}",
        )
        return Response(content=content, media_type=media_type)

    return router
