# pyright: reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnusedVariable=false, reportUnusedFunction=false
# SQLModel type stubs cause false positives; route handlers appear "unused" inside factory function

import asyncio
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

import boto3
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from metta.app_backend.auth import CheckSoftmaxUser, CheckUser
from metta.app_backend.database import db_session
from metta.app_backend.job_runner.config import get_dispatch_config
from metta.app_backend.job_runner.dispatcher import dispatch_job, presign_operation
from metta.app_backend.job_runner.job_artifacts import job_debug_key, job_logs_key
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
from metta.app_backend.otel.metrics import get_job_metrics
from metta.app_backend.queries import policy_queries
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.routes.tournament_routes import PolicyVersionSummary
from metta.app_backend.tournament.settings import JOB_TIMEOUT_SECONDS

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


class JobRequestResponse(BaseModel):
    id: UUID
    job_type: JobType
    job: dict[str, Any]
    status: JobStatus
    user_id: str
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


def _fixup_episode_job(job: JobRequest) -> None:
    if job.job.get("debug_uri") is None:
        cfg = get_dispatch_config()
        if not cfg.EVAL_S3_BUCKET:
            return
        debug_uri = presign_operation(
            "put",
            cfg.EVAL_S3_BUCKET,
            job_debug_key(job.id),
            JOB_TIMEOUT_SECONDS + 60 * 60,
            cfg.S3_PRESIGNED_ENDPOINT,
        )
        job.job = {**job.job, "debug_uri": debug_uri}


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
    async def create_jobs_batch(jobs: list[JobRequestCreate], user: CheckSoftmaxUser) -> list[UUID]:
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
        _user: CheckSoftmaxUser,
        job_type: JobType | None = Query(default=None),
        statuses: list[JobStatus] | None = Query(default=None),
        job_id: str | None = Query(default=None),
        policy_version_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> list[JobRequestResponse]:
        job_id_uuid: UUID | None = None
        policy_version_id_uuid: UUID | None = None
        if job_id:
            try:
                job_id_uuid = UUID(job_id)
            except ValueError:
                return []
        if policy_version_id:
            try:
                policy_version_id_uuid = UUID(policy_version_id)
            except ValueError:
                return []
        async with db_session() as session:
            id_query = select(JobRequest.id).order_by(col(JobRequest.created_at).desc()).offset(offset).limit(limit)
            if job_id_uuid:
                id_query = id_query.where(JobRequest.id == job_id_uuid)
            if statuses:
                id_query = id_query.where(col(JobRequest.status).in_(statuses))
            if job_type:
                id_query = id_query.where(col(JobRequest.job_type) == job_type)
            if policy_version_id_uuid:
                policy_job_ids = select(JobPolicyVersion.job_id).where(
                    JobPolicyVersion.policy_version_id == policy_version_id_uuid
                )
                id_query = id_query.where(col(JobRequest.id).in_(policy_job_ids))
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
        return responses

    @router.get("/{job_id}/logs")
    @timed_http_handler
    async def get_job_logs(job_id: UUID, _user: CheckSoftmaxUser) -> PlainTextResponse:
        async with db_session() as session:
            result = await session.execute(select(JobRequest).where(JobRequest.id == job_id))
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        cfg = get_dispatch_config()
        if not cfg.EVAL_S3_BUCKET:
            raise HTTPException(status_code=501, detail="Log storage not configured")

        def _read_logs() -> str:
            s3 = boto3.client("s3")
            resp = s3.get_object(Bucket=cfg.EVAL_S3_BUCKET, Key=job_logs_key(job_id))
            return resp["Body"].read().decode("utf-8")

        try:
            logs = await asyncio.to_thread(_read_logs)
            return PlainTextResponse(content=logs)
        except Exception as e:
            if "NoSuchKey" in type(e).__name__ or "NoSuchKey" in str(e):
                raise HTTPException(status_code=404, detail=f"No logs found for job {job_id}") from None
            logger.error(f"Failed to read logs for job {job_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to read logs") from e

    @router.get("/{job_id}/episode-stats")
    @timed_http_handler
    async def get_job_episode_stats(job_id: UUID, _user: CheckUser) -> EpisodeStatsResponse:
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

            raw_attrs = episode.attributes or {}
            parsed = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
            attributes = parsed if isinstance(parsed, dict) else {}
            stats = attributes.get("stats", {})
            agent_stats_list: list[dict[str, float]] = stats.get("agent", [])
            rewards_list: list[float] = attributes.get("rewards", [])
            game_stats: dict[str, float] = stats.get("game", {})
            steps: int | None = attributes.get("steps") or stats.get("steps")

            assignments: list[int] = job.job.get("assignments", [])
            policy_map: dict[int, JobPolicyVersion] = {jpv.position: jpv for jpv in job.policy_versions}

            policy_agents: dict[int, list[tuple[int, dict[str, float], float]]] = defaultdict(list)
            for agent_id, agent_metrics in enumerate(agent_stats_list):
                policy_idx = assignments[agent_id] if agent_id < len(assignments) else -1
                reward = rewards_list[agent_id] if agent_id < len(rewards_list) else 0.0
                policy_agents[policy_idx].append((agent_id, agent_metrics, reward))

            policy_stats: list[PolicyStatsDetail] = []
            for position in sorted(policy_agents.keys()):
                agents = policy_agents[position]
                jpv = policy_map.get(position)

                all_metric_names = set()
                for _, metrics, _ in agents:
                    all_metric_names.update(metrics.keys())

                avg_metrics: dict[str, float] = {}
                for name in sorted(all_metric_names):
                    values = [m[name] for _, m, _ in agents if name in m and m[name] is not None]
                    if values:
                        avg_metrics[name] = sum(values) / len(values)

                reward_values = [r for _, _, r in agents]
                avg_reward = sum(reward_values) / len(reward_values) if reward_values else 0.0

                agent_details = [
                    AgentStatsDetail(
                        agent_id=aid,
                        reward=reward,
                        metrics={k: v for k, v in metrics.items() if v is not None},
                    )
                    for aid, metrics, reward in agents
                ]

                pv = jpv.policy_version if jpv else None
                policy_stats.append(
                    PolicyStatsDetail(
                        position=position,
                        policy_version_id=jpv.policy_version_id if jpv else None,
                        policy_name=pv.policy.name if pv and pv.policy else None,
                        policy_version=pv.version if pv else None,
                        num_agents=len(agents),
                        avg_metrics=avg_metrics,
                        avg_reward=avg_reward,
                        agents=agent_details,
                    )
                )

            return EpisodeStatsResponse(
                game_stats=game_stats,
                policy_stats=policy_stats,
                steps=steps,
            )

    @router.get("/{job_id}")
    @timed_http_handler
    async def get_job(job_id: UUID, _user: CheckSoftmaxUser) -> JobRequestResponse:
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
            return JobRequestResponse.from_job(row)

    @router.post("/{job_id}")
    @timed_http_handler
    async def update_job(job_id: UUID, request: JobRequestUpdate, _user: CheckSoftmaxUser) -> JobRequest:
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
