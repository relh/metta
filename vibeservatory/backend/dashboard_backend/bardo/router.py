from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.queries import policy_queries
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.user_data import load_user_ids
from vibeservatory.backend.dashboard_backend.auth import SoftmaxUser
from vibeservatory.backend.dashboard_backend.database import db_session

PAGE_SIZE = 500
ACTIVE_EPISODE_JOB_STATUSES = [JobStatus.pending, JobStatus.dispatched, JobStatus.running]


class BardoPolicy(BaseModel):
    policyId: str
    policyVersionId: str
    name: str
    userId: str
    userName: str
    createdAt: str
    activeJobIds: list[str]


class BardoActiveJob(BaseModel):
    id: str
    status: JobStatus
    policyVersionIds: list[str]


class BardoWorldStateResponse(BaseModel):
    generatedAt: str
    policies: list[BardoPolicy]
    activeJobs: list[BardoActiveJob]


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _latest_policy_version(policy: Policy) -> PolicyVersion | None:
    return max(policy.versions, key=lambda version: (version.version, version.created_at), default=None)


async def _fetch_all_policies(name_filter: str | None) -> list[Policy]:
    policies: list[Policy] = []
    normalized_filter = name_filter.strip() if name_filter else None

    for offset in range(0, 1_000_000, PAGE_SIZE):
        page, _total = await policy_queries.get_policies(
            name_fuzzy=normalized_filter,
            limit=PAGE_SIZE,
            offset=offset,
        )
        policies.extend(page)
        if len(page) < PAGE_SIZE:
            break

    return policies


async def _fetch_active_episode_jobs(include_active_jobs: bool) -> list[JobRequest]:
    if not include_active_jobs:
        return []

    jobs: list[JobRequest] = []
    for offset in range(0, 1_000_000, PAGE_SIZE):
        async with db_session(read_only=True) as session:
            query = (
                select(JobRequest)
                .where(
                    col(JobRequest.job_type) == JobType.episode,
                    col(JobRequest.status).in_(ACTIVE_EPISODE_JOB_STATUSES),
                )
                .options(selectinload(JobRequest.policy_versions))
                .order_by(col(JobRequest.created_at).desc())
                .limit(PAGE_SIZE)
                .offset(offset)
            )
            page = list((await session.execute(query)).scalars().all())

        jobs.extend(page)
        if len(page) < PAGE_SIZE:
            break

    return jobs


async def _resolve_user_names(user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    users = await load_user_ids(sorted(user_ids), include_sensitive=False)
    return {user_id: (row.name or user_id) for user_id, row in users.items()}


def _normalize_active_jobs(jobs: list[JobRequest]) -> list[BardoActiveJob]:
    normalized: list[BardoActiveJob] = []
    for job in jobs:
        job_id = str(job.id).strip()
        assert job_id, "Episode jobs must have ids"
        policy_version_ids = sorted({str(entry.policy_version_id) for entry in job.policy_versions})
        normalized.append(BardoActiveJob(id=job_id, status=job.status, policyVersionIds=policy_version_ids))
    return normalized


def _collect_active_job_policy_version_usage(
    jobs: list[BardoActiveJob],
) -> dict[str, set[str]]:
    active_by_policy_version_id: defaultdict[str, set[str]] = defaultdict(set)
    for job in jobs:
        for policy_version_id in job.policyVersionIds:
            active_by_policy_version_id[policy_version_id].add(job.id)
    return dict(active_by_policy_version_id)


async def load_bardo_world_state(*, name_filter: str | None, include_active_jobs: bool) -> BardoWorldStateResponse:
    policies = await _fetch_all_policies(name_filter)
    active_jobs_raw = await _fetch_active_episode_jobs(include_active_jobs)
    latest_versions: dict[UUID, PolicyVersion] = {}
    for policy in policies:
        latest_version = _latest_policy_version(policy)
        if latest_version is None:
            continue
        latest_versions[policy.id] = latest_version

    user_names_by_id = await _resolve_user_names({policy.user_id for policy in policies})

    active_jobs = _normalize_active_jobs(active_jobs_raw)
    active_by_policy_version_id = _collect_active_job_policy_version_usage(active_jobs)

    policy_rows: list[BardoPolicy] = []
    for policy in policies:
        latest_version = latest_versions.get(policy.id)
        if latest_version is None:
            continue
        policy_version_id = str(latest_version.id)
        active_job_ids = sorted(active_by_policy_version_id.get(policy_version_id, set()))
        policy_rows.append(
            BardoPolicy(
                policyId=str(policy.id),
                policyVersionId=policy_version_id,
                name=policy.name,
                userId=policy.user_id,
                userName=user_names_by_id.get(policy.user_id, policy.user_id),
                createdAt=_isoformat_utc(latest_version.created_at),
                activeJobIds=active_job_ids,
            )
        )

    policy_rows.sort(key=lambda row: row.createdAt, reverse=True)
    return BardoWorldStateResponse(
        generatedAt=_isoformat_utc(datetime.now(UTC)),
        policies=policy_rows,
        activeJobs=active_jobs,
    )


def create_bardo_router() -> APIRouter:
    router = APIRouter(tags=["dashboard"])

    @router.get("/bardo/v1/world-state")
    @timed_http_handler
    async def get_world_state(
        _user: SoftmaxUser,
        q: str | None = Query(default=None),
    ) -> BardoWorldStateResponse:
        return await load_bardo_world_state(name_filter=q, include_active_jobs=True)

    return router
