# pyright: reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportUnusedFunction=false
# SQLModel type stubs cause false positives; route handlers appear "unused" inside factory function

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import raiseload, selectinload
from sqlmodel import col, select

from metta.app_backend.auth import NoAuthRequired
from metta.app_backend.database import DbSession
from metta.app_backend.models.episodes import Episode, EpisodeJob, EpisodePolicy, EpisodeTag
from metta.app_backend.models.job_request import JobPolicyVersion, JobRequest
from metta.app_backend.models.policies import PolicyVersion
from metta.app_backend.queries.episode_stats import EpisodeResponse, build_episode_response
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.routes.docs_routes import public_api

_EPISODE_LOAD_OPTIONS = (
    selectinload(Episode.tags),
    selectinload(Episode.episode_jobs).options(
        selectinload(EpisodeJob.job).options(
            selectinload(JobRequest.policy_versions).options(
                selectinload(JobPolicyVersion.policy_version).options(
                    selectinload(PolicyVersion.policy),
                    raiseload("*"),
                ),
                raiseload("*"),
            ),
            raiseload("*"),
        ),
        raiseload("*"),
    ),
    raiseload("*"),
)


def _build_episode_from_loaded(episode: Episode) -> EpisodeResponse:
    assignments: list[int] = []
    policy_versions: list[JobPolicyVersion] = []
    if episode.episode_jobs:
        job = episode.episode_jobs[0].job
        if job:
            assignments = job.job.get("assignments", [])
            policy_versions = job.policy_versions
    return build_episode_response(episode, assignments, policy_versions)


@public_api
def create_episode_router() -> APIRouter:
    router = APIRouter(prefix="/episodes", tags=["episodes"])

    @router.get("/{episode_id}")
    @timed_http_handler
    async def get_episode(episode_id: UUID, _user: NoAuthRequired, session: DbSession) -> EpisodeResponse:
        query = select(Episode).where(Episode.id == episode_id).options(*_EPISODE_LOAD_OPTIONS)
        episode = (await session.execute(query)).scalar_one_or_none()
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        return _build_episode_from_loaded(episode)

    @router.get("")
    @timed_http_handler
    async def list_episodes(
        _user: NoAuthRequired,
        session: DbSession,
        policy_version_id: UUID | None = Query(default=None),
        tags: str | None = Query(default=None, description="Comma-separated key:value filters"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[EpisodeResponse]:
        query = (
            select(Episode)
            .order_by(col(Episode.created_at).desc())
            .limit(limit)
            .offset(offset)
            .options(*_EPISODE_LOAD_OPTIONS)
        )

        if policy_version_id:
            subq = select(EpisodePolicy.episode_id).where(EpisodePolicy.policy_version_id == policy_version_id)
            query = query.where(col(Episode.id).in_(subq))

        if tags:
            for pair in tags.split(","):
                parts = pair.strip().split(":", 1)
                if len(parts) == 2:
                    key, value = parts
                    tag_subq = select(EpisodeTag.episode_id).where(
                        EpisodeTag.key == key.strip(), EpisodeTag.value == value.strip()
                    )
                    query = query.where(col(Episode.id).in_(tag_subq))

        episodes = (await session.execute(query)).scalars().all()
        return [_build_episode_from_loaded(ep) for ep in episodes]

    return router
