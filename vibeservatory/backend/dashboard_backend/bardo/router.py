import asyncio
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.user_data import load_user_ids
from vibeservatory.backend.dashboard_backend.auth import SoftmaxUser
from vibeservatory.backend.dashboard_backend.database import db_session

PAGE_SIZE = 500
VISIBLE_POLICY_LIMIT = 50
ACTIVE_EPISODE_JOB_STATUSES = [JobStatus.pending, JobStatus.dispatched, JobStatus.running]
WORLD_STATE_CACHE_TTL_SECONDS = 4.0
WORLD_STATE_CACHE_CONTROL = "private, no-cache"


class BardoPolicy(BaseModel):
    policyId: str
    policyVersionId: str
    name: str
    userId: str
    userName: str
    createdAt: str
    activeJobIds: list[str]
    seasonIds: list[str]


class BardoSeason(BaseModel):
    seasonId: str
    name: str
    version: int
    compatVersion: str | None
    createdAt: str
    stageCount: int
    entrantCount: int
    activeEntrantCount: int


class BardoActiveJob(BaseModel):
    id: str
    status: JobStatus
    policyVersionIds: list[str]


class BardoWorldStateResponse(BaseModel):
    generatedAt: str
    totalPolicies: int
    policies: list[BardoPolicy]
    activeJobs: list[BardoActiveJob]
    seasons: list[BardoSeason]


@dataclass
class _CachedWorldStateSnapshot:
    response: BardoWorldStateResponse
    etag: str
    expires_at_monotonic: float


_WORLD_STATE_CACHE: dict[tuple[str | None, bool], _CachedWorldStateSnapshot] = {}
_WORLD_STATE_CACHE_LOCK = asyncio.Lock()
_WORLD_STATE_COMPUTE_LOCKS: dict[tuple[str | None, bool], asyncio.Lock] = {}


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _latest_policy_version(policy: Policy) -> PolicyVersion | None:
    return max(policy.versions, key=lambda version: (version.version, version.created_at), default=None)


async def _fetch_all_policies(name_filter: str | None) -> list[Policy]:
    policies: list[Policy] = []
    normalized_filter = name_filter.strip() if name_filter else None

    for offset in range(0, 1_000_000, PAGE_SIZE):
        async with db_session(read_only=True) as session:
            query = (
                select(Policy)
                .order_by(col(Policy.created_at).desc())
                .options(selectinload(Policy.versions))
                .limit(PAGE_SIZE)
                .offset(offset)
            )
            if normalized_filter:
                query = query.where(col(Policy.name).ilike(f"%{normalized_filter}%"))
            page = list((await session.execute(query)).scalars().all())
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


async def _fetch_canonical_seasons() -> list[Season]:
    async with db_session(read_only=True) as session:
        query = (
            select(Season)
            .options(selectinload(Season.pools))
            .where(col(Season.canonical).is_(True))
            .order_by(col(Season.created_at).desc(), col(Season.name))
        )
        return list((await session.execute(query)).scalars().all())


async def _fetch_pool_player_memberships_for_seasons(
    season_ids: list[UUID],
) -> list[tuple[UUID, UUID, bool]]:
    if not season_ids:
        return []

    memberships: list[tuple[UUID, UUID, bool]] = []
    for offset in range(0, 1_000_000, PAGE_SIZE):
        async with db_session(read_only=True) as session:
            query = (
                select(Pool.season_id, PoolPlayer.policy_version_id, PoolPlayer.retired)
                .join(PoolPlayer, col(PoolPlayer.pool_id) == col(Pool.id))
                .where(col(Pool.season_id).in_(season_ids))
                .order_by(col(PoolPlayer.created_at).desc(), col(PoolPlayer.id).desc())
                .limit(PAGE_SIZE)
                .offset(offset)
            )
            page = list(await session.execute(query))

        memberships.extend(page)
        if len(page) < PAGE_SIZE:
            break

    return memberships


async def _load_canonical_season_memberships() -> tuple[list[BardoSeason], dict[str, list[str]]]:
    seasons = await _fetch_canonical_seasons()
    if not seasons:
        return [], {}

    season_ids = [season.id for season in seasons]
    membership_rows = await _fetch_pool_player_memberships_for_seasons(season_ids)

    member_ids_by_season: defaultdict[str, set[str]] = defaultdict(set)
    active_member_ids_by_season: defaultdict[str, set[str]] = defaultdict(set)
    season_ids_by_policy_version: defaultdict[str, set[str]] = defaultdict(set)

    for season_id, policy_version_id, retired in membership_rows:
        season_key = str(season_id)
        policy_version_key = str(policy_version_id)
        member_ids_by_season[season_key].add(policy_version_key)
        season_ids_by_policy_version[policy_version_key].add(season_key)
        if not retired:
            active_member_ids_by_season[season_key].add(policy_version_key)

    canonical_seasons = [
        BardoSeason(
            seasonId=str(season.id),
            name=season.name,
            version=season.version,
            compatVersion=season.compat_version,
            createdAt=_isoformat_utc(season.created_at),
            stageCount=len(season.pools),
            entrantCount=len(member_ids_by_season[str(season.id)]),
            activeEntrantCount=len(active_member_ids_by_season[str(season.id)]),
        )
        for season in seasons
    ]

    season_order = {season.seasonId: idx for idx, season in enumerate(canonical_seasons)}
    policy_season_ids = {
        policy_version_id: sorted(related_season_ids, key=lambda season_id: season_order[season_id])
        for policy_version_id, related_season_ids in season_ids_by_policy_version.items()
    }
    return canonical_seasons, policy_season_ids


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


def _stable_policy_sample_key(policy: BardoPolicy) -> tuple[str, str]:
    digest = hashlib.sha256(policy.policyId.encode("utf-8")).hexdigest()
    return digest, policy.policyId


def _limit_visible_policies(policy_rows: list[BardoPolicy], limit: int) -> list[BardoPolicy]:
    if len(policy_rows) <= limit:
        return policy_rows

    # Always keep active policies visible, then fill remaining slots with a stable sample so the lobby doesn't churn.
    active_policy_rows = [policy for policy in policy_rows if policy.activeJobIds]
    if len(active_policy_rows) >= limit:
        limited = sorted(active_policy_rows, key=_stable_policy_sample_key)[:limit]
    else:
        inactive_policy_rows = [policy for policy in policy_rows if not policy.activeJobIds]
        sampled_inactive_policy_rows = sorted(inactive_policy_rows, key=_stable_policy_sample_key)[
            : limit - len(active_policy_rows)
        ]
        limited = active_policy_rows + sampled_inactive_policy_rows

    limited.sort(key=lambda policy: policy.createdAt, reverse=True)
    return limited


async def load_bardo_world_state(*, name_filter: str | None, include_active_jobs: bool) -> BardoWorldStateResponse:
    policies = await _fetch_all_policies(name_filter)
    active_jobs_raw = await _fetch_active_episode_jobs(include_active_jobs)
    seasons, season_ids_by_policy_version = await _load_canonical_season_memberships()
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
                seasonIds=season_ids_by_policy_version.get(policy_version_id, []),
            )
        )

    policy_rows.sort(key=lambda row: row.createdAt, reverse=True)
    total_policy_count = len(policy_rows)
    if not name_filter:
        policy_rows = _limit_visible_policies(policy_rows, limit=VISIBLE_POLICY_LIMIT)

    return BardoWorldStateResponse(
        generatedAt=_isoformat_utc(datetime.now(UTC)),
        totalPolicies=total_policy_count,
        policies=policy_rows,
        activeJobs=active_jobs,
        seasons=seasons,
    )


def _normalize_etag(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:].strip()
    if normalized.startswith('"') and normalized.endswith('"') and len(normalized) >= 2:
        normalized = normalized[1:-1]
    return normalized


def _if_none_match_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    values = [value.strip() for value in if_none_match.split(",") if value.strip()]
    if "*" in values:
        return True
    normalized_etag = _normalize_etag(etag)
    return any(_normalize_etag(value) == normalized_etag for value in values)


def _world_state_cache_key(name_filter: str | None, include_active_jobs: bool) -> tuple[str | None, bool]:
    normalized_name_filter = name_filter.strip().lower() if name_filter and name_filter.strip() else None
    return (normalized_name_filter, include_active_jobs)


def _world_state_etag(response: BardoWorldStateResponse) -> str:
    payload = response.model_dump(mode="json")
    payload.pop("generatedAt", None)
    encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded_payload).hexdigest()
    return f'W/"{digest}"'


async def _world_state_compute_lock_for_key(key: tuple[str | None, bool]) -> asyncio.Lock:
    async with _WORLD_STATE_CACHE_LOCK:
        lock = _WORLD_STATE_COMPUTE_LOCKS.get(key)
        if lock is not None:
            return lock
        new_lock = asyncio.Lock()
        _WORLD_STATE_COMPUTE_LOCKS[key] = new_lock
        return new_lock


async def _load_cached_world_state_snapshot(
    *,
    name_filter: str | None,
    include_active_jobs: bool,
) -> _CachedWorldStateSnapshot:
    key = _world_state_cache_key(name_filter, include_active_jobs)
    now_monotonic = time.monotonic()
    cached = _WORLD_STATE_CACHE.get(key)
    if cached is not None and cached.expires_at_monotonic > now_monotonic:
        return cached

    lock = await _world_state_compute_lock_for_key(key)
    async with lock:
        now_monotonic = time.monotonic()
        cached = _WORLD_STATE_CACHE.get(key)
        if cached is not None and cached.expires_at_monotonic > now_monotonic:
            return cached

        response = await load_bardo_world_state(name_filter=name_filter, include_active_jobs=include_active_jobs)
        snapshot = _CachedWorldStateSnapshot(
            response=response,
            etag=_world_state_etag(response),
            expires_at_monotonic=now_monotonic + WORLD_STATE_CACHE_TTL_SECONDS,
        )
        _WORLD_STATE_CACHE[key] = snapshot
        return snapshot


def _clear_bardo_world_state_cache() -> None:
    _WORLD_STATE_CACHE.clear()
    _WORLD_STATE_COMPUTE_LOCKS.clear()


def create_bardo_router() -> APIRouter:
    router = APIRouter(tags=["dashboard"])

    @router.get("/bardo/v1/world-state")
    @timed_http_handler
    async def get_world_state(
        request: Request,
        response: Response,
        _user: SoftmaxUser,
        q: str | None = Query(default=None),
    ) -> BardoWorldStateResponse:
        snapshot = await _load_cached_world_state_snapshot(name_filter=q, include_active_jobs=True)
        response.headers["Cache-Control"] = WORLD_STATE_CACHE_CONTROL
        response.headers["ETag"] = snapshot.etag

        if _if_none_match_matches(request.headers.get("if-none-match"), snapshot.etag):
            return Response(
                status_code=304,
                headers={
                    "Cache-Control": WORLD_STATE_CACHE_CONTROL,
                    "ETag": snapshot.etag,
                },
            )

        return snapshot.response

    return router
