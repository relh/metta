import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload
from sqlmodel import col, select

# pyright: reportArgumentType=false
# SQLModel's Relationship() returns the target type, not SQLAlchemy's InstrumentedAttribute,
# causing false positives on join() and selectinload() calls.
from metta.app_backend.auth import ExternalUser, MaybeAuthenticatedUser, NoAuthRequired, SoftmaxUser
from metta.app_backend.database import db_session
from metta.app_backend.job_runner.job_artifacts import job_logs_key, read_job_artifact
from metta.app_backend.models.episodes import Episode, EpisodeJob
from metta.app_backend.models.job_request import JobPolicyVersion, JobRequest
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import (
    Match,
    MatchPlayer,
    MatchStatus,
    MembershipChange,
    MettagridEnvConfig,
    Pool,
    PoolPlayer,
    Season,
    Team,
    TeamPolicyVersion,
)
from metta.app_backend.queries.episode_stats import (
    EpisodeResponse,
    PolicyVersionSummary,
    build_episode_response,
)
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.routes.docs_routes import public_api
from metta.app_backend.tournament import registry as tournament_registry
from metta.app_backend.tournament.commissioners.base import CommissionerBase
from metta.app_backend.tournament.commissioners.factory import build_commissioner
from metta.app_backend.tournament.commissioners.teams.base import TeamCommissionerBase
from metta.app_backend.tournament.progress import StageStats, TeamTournamentProgress
from metta.app_backend.tournament.referees.teams.score_stage import ScoreStageReferee
from metta.app_backend.tournament.season_resolver import get_season_versions, parse_season_ref, resolve_season
from metta.app_backend.tournament.settings import DEFAULT_SEASON, HIDDEN_SEASONS
from metta.app_backend.tournament.stage_stats import build_stage_stats_row, load_stage_stats_counts

logger = logging.getLogger(__name__)


async def get_session():
    async with db_session() as session:
        yield session


class LeaderboardEntry(BaseModel):
    rank: int = Field(description="1-indexed position on the leaderboard")
    policy: PolicyVersionSummary = Field(description="Identity of the ranked policy version")
    score: float = Field(description="Elo or rating score")
    matches: int = Field(description="Number of matches played")


class ScorePoliciesLeaderboardEntry(BaseModel):
    rank: int = Field(description="1-indexed position on the score-policies leaderboard")
    policy: PolicyVersionSummary = Field(description="Identity of the ranked policy version")
    placement_score: float = Field(
        description=(
            "Sum of a policy's best team placements (top_k). "
            "Missing appearances are penalized as (total ranked teams + 1)."
        )
    )
    team_appearances: int = Field(description="Number of ranked teams containing this policy")
    team_ranks: list[int] = Field(
        description=(
            "Sorted 1-indexed team ranks where this policy appears in the source team pool used for "
            "score-policies placement scoring"
        )
    )


class PoolMembership(BaseModel):
    pool_name: str = Field(description="Name of the pool")
    active: bool = Field(description="Whether the policy is currently active in this pool")
    completed: int = Field(description="Number of completed matches")
    failed: int = Field(description="Number of failed matches")
    pending: int = Field(description="Number of pending matches")


class PolicySummary(BaseModel):
    policy: PolicyVersionSummary = Field(description="Identity of the policy version")
    pools: list[PoolMembership] = Field(description="Pool membership details for this policy")
    entered_at: str = Field(description="ISO 8601 timestamp of when the policy entered the season")


class SubmitRequest(BaseModel):
    policy_version_id: UUID = Field(description="ID of the policy version to submit")


class SubmitResponse(BaseModel):
    pools: list[str] = Field(description="Names of pools the policy was added to")


class MatchPlayerInfo(BaseModel):
    policy: PolicyVersionSummary = Field(description="Identity of the participating policy version")
    num_agents: int = Field(description="Number of agents controlled by this policy in the match")
    score: float | None = Field(description="Score awarded to this player, if the match completed")


class MatchResponse(BaseModel):
    id: UUID = Field(description="Unique match identifier")
    season_name: str = Field(description="Name of the season this match belongs to")
    pool_name: str = Field(description="Name of the pool this match was played in")
    status: str = Field(description="Match status: pending, running, completed, or failed")
    assignments: list[int] = Field(description="Per-agent policy index assignment")
    players: list[MatchPlayerInfo] = Field(description="Participating policies and their results")
    error: str | None = Field(description="Error message if the match failed")
    episode_id: UUID | None = Field(description="Episode identifier, present if a game was recorded")
    episode: EpisodeResponse | None = Field(default=None, description="Full episode data, included in detail responses")
    created_at: datetime = Field(description="When the match was created")


class TeamCogSummary(BaseModel):
    position: int = Field(description="0-indexed slot position of this cog inside the team")
    policy: PolicyVersionSummary = Field(description="Policy version backing this team slot")


class TeamSummary(BaseModel):
    id: UUID = Field(description="Unique team identifier")
    pool_name: str = Field(description="Name of the pool (stage bucket) where this team record exists")
    eliminated: bool = Field(description="Whether this team was culled in its team-eval round")
    score: float | None = Field(
        description="Team score computed for elimination ranking in its current round, if scored"
    )
    matches: int = Field(default=0, description="Number of completed match records linked to this team_id")
    cogs: list[TeamCogSummary] = Field(
        description="Ordered team composition; each cog is one slot containing a policy version"
    )
    created_at: str = Field(description="ISO 8601 timestamp when this team row was created")


class MembershipHistoryEntry(BaseModel):
    season_name: str = Field(description="Name of the season")
    season_version: int | None = Field(description="Version of the season")
    pool_name: str = Field(description="Name of the pool")
    action: str = Field(description="Membership action (e.g. added, removed, retired)")
    notes: str | None = Field(description="Optional notes about the membership change")
    created_at: str = Field(description="ISO 8601 timestamp of the membership change")


class PoolInfo(BaseModel):
    id: UUID | None = Field(default=None, description="Database identifier of the pool")
    name: str = Field(description="Name of the pool")
    description: str = Field(description="Human-readable description of the pool")
    config_id: UUID | None = Field(default=None, description="Identifier of the pool's environment configuration")


class SeasonVersionInfo(BaseModel):
    version: int = Field(description="Season version number")
    canonical: bool = Field(description="Whether this is the canonical (active) version")
    disabled_at: str | None = Field(description="ISO 8601 timestamp when this version was disabled")
    created_at: str = Field(description="ISO 8601 timestamp when this version was created")
    compat_version: str | None = Field(default=None, description="Compatibility version string (e.g. '0.4')")


class SeasonSummary(BaseModel):
    id: UUID = Field(description="Unique season identifier")
    name: str = Field(description="Short name of the season")
    version: int = Field(description="Season version number")
    canonical: bool = Field(description="Whether this is the canonical (active) version")
    summary: str = Field(description="Human-readable description of the season")
    entry_pool: str | None = Field(default=None, description="Name of the pool where new policies are submitted")
    leaderboard_pool: str | None = Field(default=None, description="Name of the pool used for the leaderboard")
    is_default: bool = Field(description="Whether this is the default season")
    compat_version: str | None = Field(default=None, description="Compatibility version string (e.g. '0.4')")
    pools: list[PoolInfo] = Field(description="Pools in this season")

    @classmethod
    async def from_commissioner(
        cls,
        season: Season,
        season_name: str,
        pools_by_name: dict[str, Pool] | None = None,
    ) -> "SeasonSummary":
        if season_name not in tournament_registry.SEASONS:
            return cls(
                id=season.id,
                name=season_name,
                version=season.version,
                canonical=season.canonical,
                summary="",
                entry_pool=None,
                leaderboard_pool=None,
                is_default=False,
                compat_version=season.compat_version,
                pools=[],
            )

        commissioner = await build_commissioner(season_name, season_id=season.id)
        desc = commissioner.description_for_version(season.version)
        db_pools = pools_by_name or {}
        return cls(
            id=season.id,
            name=season_name,
            version=season.version,
            canonical=season.canonical,
            summary=desc.summary,
            entry_pool=commissioner.entry_pool,
            leaderboard_pool=commissioner.leaderboard_pool,
            is_default=season_name == DEFAULT_SEASON,
            compat_version=season.compat_version,
            pools=[
                PoolInfo(
                    id=db_pools[p.name].id if p.name in db_pools else None,
                    name=p.name,
                    description=p.description,
                    config_id=db_pools[p.name].env_config_id if p.name in db_pools else None,
                )
                for p in desc.pools
            ],
        )


class SeasonDetail(SeasonSummary):
    status: Literal["not_started", "in_progress", "complete"] = Field(
        description="High-level tournament status inferred from season/progress state"
    )
    display_name: str = Field(description="Human-readable season title for UI display")
    started_at: str | None = Field(default=None, description="ISO 8601 timestamp when the season was started")
    tournament_type: Literal["policy", "team"] = Field(description="Tournament format")
    entrant_count: int = Field(description="Unique policy versions that have entered the season")
    active_entrant_count: int = Field(description="Unique non-retired policy versions still active in the season")
    match_count: int = Field(description="Total matches created across all pools in this season")
    stage_count: int = Field(description="Number of configured stages")

    @classmethod
    async def from_commissioner(
        cls,
        season: Season,
        season_name: str,
        counts: tuple[int, int, int],
        pools_by_name: dict[str, Pool] | None = None,
    ) -> "SeasonDetail":
        commissioner = await build_commissioner(season_name, season_id=season.id)
        desc = commissioner.description_for_version(season.version)
        entrant_count, active_entrant_count, match_count = counts
        tournament_type: Literal["policy", "team"] = "policy"
        status = _infer_policy_season_status(season, match_count)
        stage_count = len(desc.pools)
        if isinstance(commissioner, TeamCommissionerBase):
            tournament_type = "team"
            progress = await commissioner.get_progress()
            status = _infer_team_season_status(season, progress)
            stage_count = len(progress.stage_flow)
        db_pools = pools_by_name or {}
        return cls(
            id=season.id,
            name=season_name,
            version=season.version,
            canonical=season.canonical,
            summary=desc.summary,
            entry_pool=commissioner.entry_pool,
            leaderboard_pool=commissioner.leaderboard_pool,
            is_default=season_name == DEFAULT_SEASON,
            compat_version=season.compat_version,
            pools=[
                PoolInfo(
                    id=db_pools[p.name].id if p.name in db_pools else None,
                    name=p.name,
                    description=p.description,
                    config_id=db_pools[p.name].env_config_id if p.name in db_pools else None,
                )
                for p in desc.pools
            ],
            status=status,
            display_name=commissioner.display_name,
            started_at=season.started_at.isoformat() if season.started_at else None,
            tournament_type=tournament_type,
            entrant_count=entrant_count,
            active_entrant_count=active_entrant_count,
            match_count=match_count,
            stage_count=stage_count,
        )


def _infer_policy_season_status(season: Season, match_count: int) -> Literal["not_started", "in_progress", "complete"]:
    if season.disabled_at is not None:
        return "complete"
    if season.started_at is None and match_count == 0:
        return "not_started"
    return "in_progress"


def _infer_team_season_status(
    season: Season,
    progress: TeamTournamentProgress,
) -> Literal["not_started", "in_progress", "complete"]:
    if season.disabled_at is not None:
        return "complete"
    if not progress.started:
        return "not_started"
    if progress.phase == "complete":
        return "complete"
    return "in_progress"


async def _get_pools_by_name(session: AsyncSession, season_id: UUID) -> dict[str, Pool]:
    pools = (await session.execute(select(Pool).where(Pool.season_id == season_id))).scalars().all()
    return {p.name: p for p in pools if p.name}


async def _resolve_season_or_404(
    session: AsyncSession,
    season_name: str,
    *,
    allow_hidden: bool = False,
) -> tuple[str, Season]:
    name, version = parse_season_ref(season_name)
    if name not in tournament_registry.SEASONS or (name in HIDDEN_SEASONS and not allow_hidden):
        raise HTTPException(status_code=404, detail="Season not found")
    season = await resolve_season(session, name, version)
    if not season:
        raise HTTPException(status_code=404, detail="Season version not found")
    return name, season


async def _load_policy_version_summaries(
    session: AsyncSession,
    policy_version_ids: list[UUID],
) -> dict[UUID, PolicyVersionSummary]:
    if not policy_version_ids:
        return {}

    pvs_result = (
        (
            await session.execute(
                select(PolicyVersion)
                .where(col(PolicyVersion.id).in_(policy_version_ids))
                .options(selectinload(PolicyVersion.policy))
            )
        )
        .scalars()
        .all()
    )
    return {pv.id: PolicyVersionSummary.from_model(pv) for pv in pvs_result}


async def _resolve_season_and_commissioner_or_404(
    session: AsyncSession,
    season_name: str,
    *,
    allow_hidden: bool = False,
) -> tuple[str, Season, CommissionerBase]:
    name, season = await _resolve_season_or_404(session, season_name, allow_hidden=allow_hidden)
    commissioner = await build_commissioner(name, season_id=season.id)
    return name, season, commissioner


async def _resolve_team_commissioner_or_400(
    session: AsyncSession,
    season_name: str,
    *,
    allow_hidden: bool = False,
    detail: str,
) -> tuple[str, Season, TeamCommissionerBase]:
    name, season, commissioner = await _resolve_season_and_commissioner_or_404(
        session,
        season_name,
        allow_hidden=allow_hidden,
    )
    if not isinstance(commissioner, TeamCommissionerBase):
        raise HTTPException(status_code=400, detail=detail)
    return name, season, commissioner


async def _build_policy_leaderboard(
    session: AsyncSession,
    commissioner: CommissionerBase,
    *,
    pool_name: str | None = None,
) -> list[LeaderboardEntry]:
    leaderboard = await commissioner.get_leaderboard(pool_name=pool_name)
    if not leaderboard:
        return []

    pv_ids = [pv_id for pv_id, _, _ in leaderboard]
    policy_summaries = await _load_policy_version_summaries(session, pv_ids)
    return [
        LeaderboardEntry(
            rank=i + 1,
            policy=policy_summaries.get(pv_id, PolicyVersionSummary(id=pv_id, name=None, version=None)),
            score=score,
            matches=match_count,
        )
        for i, (pv_id, score, match_count) in enumerate(leaderboard)
    ]


async def _build_score_policies_leaderboard(
    session: AsyncSession,
    commissioner: TeamCommissionerBase,
) -> list[ScorePoliciesLeaderboardEntry]:
    row = (
        await session.execute(
            select(Pool, Season.version)
            .join(Pool.season)
            .where(Pool.season_id == commissioner.season_id)
            .where(Pool.name == commissioner.leaderboard_pool)
        )
    ).one_or_none()
    if row is None:
        return []
    pool, season_version = row

    score_referee = commissioner.get_referees(season_version).get(commissioner.leaderboard_pool)
    assert isinstance(score_referee, ScoreStageReferee)

    leaderboard = await score_referee.get_leaderboard_with_team_ranks(pool.id)
    if not leaderboard:
        return []

    pv_ids = [pv_id for pv_id, _, _ in leaderboard]
    policy_summaries = await _load_policy_version_summaries(session, pv_ids)
    return [
        ScorePoliciesLeaderboardEntry(
            rank=i + 1,
            policy=policy_summaries.get(pv_id, PolicyVersionSummary(id=pv_id, name=None, version=None)),
            placement_score=score,
            team_appearances=len(team_ranks),
            team_ranks=team_ranks,
        )
        for i, (pv_id, score, team_ranks) in enumerate(leaderboard)
    ]


async def _build_team_summaries(
    session: AsyncSession,
    *,
    season_id: UUID,
    limit: int = 50,
    offset: int = 0,
    pool_name: str | None = None,
    eliminated: bool | None = None,
    policy_version_id: UUID | None = None,
) -> list[TeamSummary]:
    query = (
        select(Team)
        .join(Team.pool)
        .where(Pool.season_id == season_id)
        .options(
            selectinload(Team.policy_versions).options(
                selectinload(TeamPolicyVersion.policy_version).options(
                    selectinload(PolicyVersion.policy),
                    raiseload("*"),
                ),
                raiseload("*"),
            ),
            selectinload(Team.pool).raiseload("*"),
            raiseload("*"),
        )
    )

    if pool_name is not None:
        query = query.where(Pool.name == pool_name)
    if eliminated is not None:
        query = query.where(Team.eliminated == eliminated)
    if policy_version_id is not None:
        subq = select(TeamPolicyVersion.team_id).where(TeamPolicyVersion.policy_version_id == policy_version_id)
        query = query.where(col(Team.id).in_(subq))

    query = query.order_by(Team.score.desc().nulls_last(), col(Team.created_at).desc()).limit(limit).offset(offset)  # type: ignore[union-attr]

    teams = (await session.execute(query)).scalars().all()
    team_ids = [t.id for t in teams]
    match_counts: dict[UUID, int] = {}
    if team_ids:
        match_rows = await session.execute(
            select(Match.team_id, func.count())
            .where(col(Match.team_id).in_(team_ids))
            .where(Match.status == MatchStatus.completed)
            .group_by(Match.team_id)
        )
        match_counts = {row[0]: row[1] for row in match_rows.all() if row[0] is not None}

    return [
        TeamSummary(
            id=t.id,
            pool_name=t.pool.name or "",
            eliminated=t.eliminated,
            score=t.score,
            matches=match_counts.get(t.id, 0),
            cogs=[
                TeamCogSummary(
                    position=tpv.position,
                    policy=PolicyVersionSummary.from_model(tpv.policy_version),
                )
                for tpv in sorted(t.policy_versions, key=lambda c: c.position)
            ],
            created_at=t.created_at.isoformat(),
        )
        for t in teams
    ]


@public_api
def create_tournament_router() -> APIRouter:
    router = APIRouter(prefix="/tournament", tags=["tournament"])

    @router.get("/seasons")
    @timed_http_handler
    async def list_seasons(_user: NoAuthRequired, session: AsyncSession = Depends(get_session)) -> list[SeasonSummary]:
        seasons = (
            (
                await session.execute(
                    select(Season).where(col(Season.name).not_in(HIDDEN_SEASONS), col(Season.canonical).is_(True))
                )
            )
            .scalars()
            .all()
        )
        results: list[SeasonSummary] = []
        for season in seasons:
            pools_by_name = await _get_pools_by_name(session, season.id)
            results.append(await SeasonSummary.from_commissioner(season, season.name, pools_by_name))
        return results

    @router.get("/seasons/{season_name}")
    @timed_http_handler
    async def get_season(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include leaderboard of a hidden season (for testing)"),
    ) -> SeasonDetail:
        name, season = await _resolve_season_or_404(session, season_name, allow_hidden=include_hidden)
        entrant_count = (
            await session.execute(
                select(func.count(func.distinct(PoolPlayer.policy_version_id)))
                .select_from(Pool)
                .join(PoolPlayer, PoolPlayer.pool_id == Pool.id)
                .where(Pool.season_id == season.id)
            )
        ).scalar_one()
        active_entrant_count = (
            await session.execute(
                select(func.count(func.distinct(PoolPlayer.policy_version_id)))
                .select_from(Pool)
                .join(PoolPlayer, PoolPlayer.pool_id == Pool.id)
                .where(Pool.season_id == season.id, col(PoolPlayer.retired).is_(False))
            )
        ).scalar_one()
        match_count = (
            await session.execute(
                select(func.count(Match.id))
                .select_from(Pool)
                .join(Match, Match.pool_id == Pool.id)
                .where(Pool.season_id == season.id)
            )
        ).scalar_one()
        pools_by_name = await _get_pools_by_name(session, season.id)
        return await SeasonDetail.from_commissioner(
            season,
            name,
            (int(entrant_count), int(active_entrant_count), int(match_count)),
            pools_by_name,
        )

    @router.get("/seasons/{season_name}/pools/{pool_name}/config")
    @timed_http_handler
    async def get_pool_config(
        season_name: str, pool_name: str, _user: NoAuthRequired, session: AsyncSession = Depends(get_session)
    ) -> JSONResponse:
        _, season = await _resolve_season_or_404(session, season_name)
        pool = (
            await session.execute(
                select(Pool)
                .where(Pool.season_id == season.id)
                .where(Pool.name == pool_name)
                .options(selectinload(Pool.env_config))
            )
        ).scalar_one_or_none()
        if not pool or not pool.env_config:
            raise HTTPException(status_code=404, detail="Pool config not found")
        return JSONResponse(content=pool.env_config.config)

    @router.get("/configs/{config_id}")
    @timed_http_handler
    async def get_config(
        config_id: UUID, _user: NoAuthRequired, session: AsyncSession = Depends(get_session)
    ) -> JSONResponse:
        env_config = (await session.execute(select(MettagridEnvConfig).filter_by(id=config_id))).scalar_one_or_none()
        if not env_config:
            raise HTTPException(status_code=404, detail="Config not found")
        return JSONResponse(content=env_config.config)

    @router.get("/seasons/{season_name}/versions")
    @timed_http_handler
    async def list_season_versions(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
    ) -> list[SeasonVersionInfo]:
        name, _ = parse_season_ref(season_name)
        versions = await get_season_versions(session, name)
        if not versions:
            raise HTTPException(status_code=404, detail="Season not found")

        return [
            SeasonVersionInfo(
                version=s.version,
                canonical=s.canonical,
                disabled_at=s.disabled_at.isoformat() if s.disabled_at else None,
                created_at=s.created_at.isoformat(),
                compat_version=s.compat_version,
            )
            for s in versions
        ]

    @router.get("/seasons/{season_name}/leaderboard")
    @timed_http_handler
    async def get_leaderboard(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include leaderboard of a hidden season (for testing)"),
        pool: str | None = Query(default=None, description="Pool name to scope leaderboard to (overrides default)"),
    ) -> list[LeaderboardEntry]:
        _, _, commissioner = await _resolve_season_and_commissioner_or_404(
            session,
            season_name,
            allow_hidden=include_hidden,
        )
        return await _build_policy_leaderboard(session, commissioner, pool_name=pool)

    @router.get("/seasons/{season_name}/score-policies-leaderboard")
    @timed_http_handler
    async def get_score_policies_leaderboard(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include leaderboard of a hidden season (for testing)"),
    ) -> list[ScorePoliciesLeaderboardEntry]:
        _, _, commissioner = await _resolve_team_commissioner_or_400(
            session,
            season_name,
            allow_hidden=include_hidden,
            detail="Score-policies leaderboard is only available for team seasons",
        )
        return await _build_score_policies_leaderboard(session, commissioner)

    @router.get("/seasons/{season_name}/policies")
    @timed_http_handler
    async def get_policies(
        season_name: str,
        user: MaybeAuthenticatedUser,
        session: AsyncSession = Depends(get_session),
        mine: bool = Query(default=False, description="Filter to only policies owned by the authenticated user"),
        include_hidden: bool = Query(
            default=False, description="Include policies that are part of a hidden season (for testing)"
        ),
    ) -> list[PolicySummary]:
        _, season = await _resolve_season_or_404(session, season_name, allow_hidden=include_hidden)
        query = (
            select(PolicyVersion)
            .join(PolicyVersion.pool_players)
            .join(PoolPlayer.pool)
            .where(Pool.season_id == season.id)
            .options(
                selectinload(PolicyVersion.policy),
                selectinload(PolicyVersion.pool_players).selectinload(PoolPlayer.pool).selectinload(Pool.season),
            )
            .distinct()
        )

        if mine:
            if user:
                query = query.join(PolicyVersion.policy).where(Policy.user_id == user.id)
            else:
                raise HTTPException(status_code=401, detail="Authentication required for mine=true")

        policy_versions = (await session.execute(query)).scalars().all()

        if not policy_versions:
            return []

        counts_query = (
            select(
                PoolPlayer.policy_version_id,
                col(Pool.name).label("pool_name"),  # type: ignore
                Match.status,
                func.count().label("count"),
            )
            .join(MatchPlayer.match)
            .join(MatchPlayer.pool_player)
            .join(PoolPlayer.pool)
            .where(Pool.season_id == season.id)
            .group_by(PoolPlayer.policy_version_id, Pool.name, Match.status)
        )
        counts_rows = (await session.execute(counts_query)).all()

        match_counts: dict[tuple[UUID, str], dict[str, int]] = {}
        for pv_id, pool_name, status, count in counts_rows:
            key = (pv_id, pool_name)
            if key not in match_counts:
                match_counts[key] = {"completed": 0, "failed": 0, "pending": 0}
            if status == MatchStatus.completed:
                match_counts[key]["completed"] += count
            elif status == MatchStatus.failed:
                match_counts[key]["failed"] += count
            else:
                match_counts[key]["pending"] += count

        def get_pool_membership(pv_id: UUID, pp: PoolPlayer) -> PoolMembership:
            pool_name = pp.pool.name or "unknown"
            counts = match_counts.get((pv_id, pool_name), {"completed": 0, "failed": 0, "pending": 0})
            return PoolMembership(
                pool_name=pool_name,
                active=not pp.retired,
                completed=counts["completed"],
                failed=counts["failed"],
                pending=counts["pending"],
            )

        results = []
        for pv in policy_versions:
            season_pool_players = [pp for pp in pv.pool_players if pp.pool.season_id == season.id]
            if not season_pool_players:
                continue
            results.append(
                PolicySummary(
                    policy=PolicyVersionSummary.from_model(pv),
                    pools=[get_pool_membership(pv.id, pp) for pp in season_pool_players],
                    entered_at=min(pp.created_at for pp in season_pool_players).isoformat(),
                )
            )

        return sorted(results, key=lambda x: x.entered_at, reverse=True)

    def _match_response(
        m: Match,
        season_name: str,
        episode_id: str | None,
        error: str | None,
        *,
        episode: EpisodeResponse | None = None,
    ) -> MatchResponse:
        assignments = m.assignments or []
        agent_counts: dict[int, int] = {}
        for idx in assignments:
            agent_counts[idx] = agent_counts.get(idx, 0) + 1

        players = [
            MatchPlayerInfo(
                policy=PolicyVersionSummary.from_model(mp.pool_player.policy_version),
                num_agents=agent_counts.get(mp.policy_index, 0),
                score=mp.score,
            )
            for mp in sorted(m.players, key=lambda p: p.policy_index)
        ]

        ep_id: UUID | None = None
        if episode_id:
            ep_id = UUID(episode_id)

        return MatchResponse(
            id=m.id,
            season_name=season_name,
            pool_name=m.pool.name,
            status=m.status.value,
            assignments=assignments,
            players=players,
            error=error if m.status == MatchStatus.failed else None,
            episode_id=ep_id,
            episode=episode,
            created_at=m.created_at,
        )

    @router.get("/seasons/{season_name}/matches")
    @timed_http_handler
    async def get_matches(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        limit: int = 50,
        offset: int = 0,
        include_hidden: bool = Query(default=False, description="Include matches of a hidden season (for testing)"),
        pool_names: list[str] | None = Query(default=None),
        policy_version_ids: list[UUID] | None = Query(default=None),
    ) -> list[MatchResponse]:
        name, season = await _resolve_season_or_404(session, season_name, allow_hidden=include_hidden)
        query = (
            select(Match, JobRequest.episode_id, JobRequest.error)
            .outerjoin(Match.job)
            .join(Match.pool)
            .where(Pool.season_id == season.id)
        )

        if pool_names:
            query = query.where(col(Pool.name).in_(pool_names))

        if policy_version_ids:
            for pv_id in policy_version_ids:
                subq = (
                    select(MatchPlayer.match_id)
                    .join(MatchPlayer.pool_player)
                    .where(PoolPlayer.policy_version_id == pv_id)
                )
                query = query.where(col(Match.id).in_(subq))

        query = (
            query.order_by(col(Match.created_at).desc())
            .limit(limit)
            .offset(offset)
            .options(
                selectinload(Match.players).options(
                    selectinload(MatchPlayer.pool_player).options(
                        selectinload(PoolPlayer.policy_version).options(
                            selectinload(PolicyVersion.policy),
                            raiseload("*"),
                        ),
                        raiseload("*"),
                    ),
                    raiseload("*"),
                ),
                selectinload(Match.pool).raiseload("*"),
                raiseload("*"),
            )
        )

        rows = (await session.execute(query)).all()
        if not rows:
            return []

        return [_match_response(m, name, episode_id, error) for m, episode_id, error in rows]

    @router.get("/matches/{match_id}")
    @timed_http_handler
    async def get_match(
        match_id: UUID, _user: NoAuthRequired, session: AsyncSession = Depends(get_session)
    ) -> MatchResponse:
        query = (
            select(Match)
            .where(Match.id == match_id)
            .options(
                selectinload(Match.players).options(
                    selectinload(MatchPlayer.pool_player).options(
                        selectinload(PoolPlayer.policy_version).options(
                            selectinload(PolicyVersion.policy),
                            raiseload("*"),
                        ),
                        raiseload("*"),
                    ),
                    raiseload("*"),
                ),
                selectinload(Match.pool).options(
                    selectinload(Pool.season).raiseload("*"),
                    raiseload("*"),
                ),
                selectinload(Match.job).options(
                    selectinload(JobRequest.policy_versions).options(
                        selectinload(JobPolicyVersion.policy_version).options(
                            selectinload(PolicyVersion.policy),
                            raiseload("*"),
                        ),
                        raiseload("*"),
                    ),
                    selectinload(JobRequest.episode_jobs).options(
                        selectinload(EpisodeJob.episode).options(
                            selectinload(Episode.tags),
                            raiseload("*"),
                        ),
                        raiseload("*"),
                    ),
                    raiseload("*"),
                ),
                raiseload("*"),
            )
        )
        m = (await session.execute(query)).scalar_one_or_none()
        if not m:
            raise HTTPException(status_code=404, detail="Match not found")

        job = m.job
        episode_id_str = job.episode_id if job else None
        error = job.error if job else None
        season_name = m.pool.season.name if m.pool and m.pool.season else "unknown"

        episode_resp: EpisodeResponse | None = None
        if job and job.episode_jobs:
            episode = job.episode_jobs[0].episode
            if episode:
                assignments: list[int] = job.job.get("assignments", [])
                episode_resp = build_episode_response(episode, assignments, job.policy_versions)

        return _match_response(m, season_name, episode_id_str, error, episode=episode_resp)

    MATCH_ARTIFACT_TYPES = {"logs": (job_logs_key, "text/plain")}

    @router.get("/matches/{match_id}/{policy_version_id}/artifacts/{artifact_type}")
    @timed_http_handler
    async def get_match_artifact(
        match_id: UUID,
        policy_version_id: UUID,
        artifact_type: str,
        user: ExternalUser,
        session: AsyncSession = Depends(get_session),
    ) -> Response:
        if artifact_type not in MATCH_ARTIFACT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_type}")

        match = (
            await session.execute(
                select(Match)
                .where(Match.id == match_id)
                .options(
                    selectinload(Match.players)
                    .raiseload("*")
                    .selectinload(MatchPlayer.pool_player)
                    .raiseload("*")
                    .selectinload(PoolPlayer.policy_version)
                    .raiseload("*")
                    .selectinload(PolicyVersion.policy)
                    .raiseload("*"),
                    raiseload("*"),
                )
            )
        ).scalar_one_or_none()
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        if not match.job_id:
            raise HTTPException(status_code=404, detail="Match has no associated job")

        pv_player = next((mp for mp in match.players if mp.pool_player.policy_version_id == policy_version_id), None)
        if not pv_player:
            raise HTTPException(status_code=403, detail="Policy is not a participant in this match")
        if pv_player.pool_player.policy_version.policy.user_id != user.id:
            raise HTTPException(status_code=403, detail="You do not own this policy")

        key_fn, media_type = MATCH_ARTIFACT_TYPES[artifact_type]
        content, content_type = await read_job_artifact(match.job_id, key_fn, media_type, artifact_label=artifact_type)
        return Response(content=content, media_type=content_type)

    @router.post("/seasons/{season_name}/submissions")
    @timed_http_handler
    async def submit_policy(
        season_name: str, request: SubmitRequest, _user: ExternalUser, session: AsyncSession = Depends(get_session)
    ) -> SubmitResponse:
        _, version = parse_season_ref(season_name)
        if version is not None:
            raise HTTPException(status_code=400, detail="Submitting to a season version is not supported")
        _, season, commissioner = await _resolve_season_and_commissioner_or_404(session, season_name)
        existing = (
            await session.execute(
                select(PoolPlayer)
                .join(PoolPlayer.pool)
                .where(Pool.season_id == season.id)
                .where(PoolPlayer.policy_version_id == request.policy_version_id)
                .limit(1)
            )
        ).scalar_one_or_none()

        if existing:
            raise HTTPException(status_code=409, detail="Policy already submitted to this season")

        pool_names = await commissioner.submit(request.policy_version_id)
        return SubmitResponse(pools=pool_names)

    @router.get("/policies/{policy_version_id}/memberships")
    @timed_http_handler
    async def get_policy_memberships(
        policy_version_id: UUID, _user: NoAuthRequired, session: AsyncSession = Depends(get_session)
    ) -> list[MembershipHistoryEntry]:
        changes = (
            (
                await session.execute(
                    select(MembershipChange)
                    .join(MembershipChange.pool_player)
                    .join(PoolPlayer.pool)
                    .join(Pool.season)
                    .where(PoolPlayer.policy_version_id == policy_version_id)
                    .order_by(
                        col(MembershipChange.created_at).desc(),
                        col(MembershipChange.action).asc(),
                    )
                    .options(
                        selectinload(MembershipChange.pool_player)
                        .selectinload(PoolPlayer.pool)
                        .selectinload(Pool.season)
                    )
                )
            )
            .scalars()
            .all()
        )

        return [
            MembershipHistoryEntry(
                season_name=c.pool_player.pool.season.name if c.pool_player.pool.season else "unknown",
                season_version=c.pool_player.pool.season.version if c.pool_player.pool.season else None,
                pool_name=c.pool_player.pool.name or "unknown",
                action=c.action.value,
                notes=c.notes,
                created_at=c.created_at.isoformat(),
            )
            for c in changes
        ]

    @router.get("/my-memberships")
    @timed_http_handler
    async def get_my_memberships(
        user: ExternalUser, session: AsyncSession = Depends(get_session)
    ) -> dict[str, list[str]]:
        """Get all season memberships for the authenticated user's policy versions.

        Returns a mapping of policy_version_id -> list of season names.
        """
        rows = (
            await session.execute(
                select(PoolPlayer.policy_version_id, Season.name)
                .join(PoolPlayer.pool)
                .join(Pool.season)
                .join(PoolPlayer.policy_version)
                .join(PolicyVersion.policy)
                .where(Policy.user_id == user.id)
                .distinct()
            )
        ).all()

        result: dict[str, list[str]] = {}
        for pv_id, season_name in rows:
            pv_id_str = str(pv_id)
            if pv_id_str not in result:
                result[pv_id_str] = []
            result[pv_id_str].append(season_name)

        return result

    @router.get("/seasons/{season_name}/progress")
    @timed_http_handler
    async def get_progress(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include hidden season progress (for testing)"),
    ) -> TeamTournamentProgress:
        _, _, commissioner = await _resolve_team_commissioner_or_400(
            session,
            season_name,
            allow_hidden=include_hidden,
            detail="Progress not available for this season type",
        )
        return await commissioner.get_progress()

    @router.post("/seasons/{season_name}/start")
    @timed_http_handler
    async def start_season(
        season_name: str,
        _user: SoftmaxUser,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include hidden seasons (for testing)"),
    ) -> TeamTournamentProgress:
        _, season, commissioner = await _resolve_team_commissioner_or_400(
            session,
            season_name,
            allow_hidden=include_hidden,
            detail="Only team seasons can be started",
        )
        if season.started_at is not None:
            raise HTTPException(status_code=409, detail="Season already started")

        season.started_at = datetime.now(UTC)
        session.add(season)
        await session.commit()
        return await commissioner.get_progress()

    @router.get("/seasons/{season_name}/teams")
    @timed_http_handler
    async def get_teams(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        limit: int = 50,
        offset: int = 0,
        pool_name: str | None = Query(default=None),
        eliminated: bool | None = Query(default=None),
        policy_version_id: UUID | None = Query(default=None),
        include_hidden: bool = Query(default=False, description="Include hidden season teams (for testing)"),
    ) -> list[TeamSummary]:
        _, season = await _resolve_season_or_404(session, season_name, allow_hidden=include_hidden)
        return await _build_team_summaries(
            session,
            season_id=season.id,
            limit=limit,
            offset=offset,
            pool_name=pool_name,
            eliminated=eliminated,
            policy_version_id=policy_version_id,
        )

    @router.get("/seasons/{season_name}/stages")
    @timed_http_handler
    async def get_stages(
        season_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include hidden season stages (for testing)"),
    ) -> list[StageStats]:
        _, season = await _resolve_season_or_404(session, season_name, allow_hidden=include_hidden)
        pools = (
            (await session.execute(select(Pool).where(Pool.season_id == season.id).order_by(Pool.created_at)))
            .scalars()
            .all()
        )
        counts = await load_stage_stats_counts(
            session,
            {pool.id for pool in pools},
            include_retired_policies=True,
        )

        results: list[StageStats] = []
        for pool in pools:
            if not pool.name:
                continue
            results.append(build_stage_stats_row(pool.name, pool, counts))

        return results

    @router.get("/seasons/{season_name}/leaderboard/{leaderboard_type}/{pool_name}")
    @timed_http_handler
    async def get_stage_leaderboard_by_type(
        season_name: str,
        leaderboard_type: Literal["policy", "team", "score-policies"],
        pool_name: str,
        _user: NoAuthRequired,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include leaderboard of a hidden season (for testing)"),
    ) -> list[LeaderboardEntry] | list[TeamSummary] | list[ScorePoliciesLeaderboardEntry]:
        if leaderboard_type == "policy":
            _, _, commissioner = await _resolve_season_and_commissioner_or_404(
                session,
                season_name,
                allow_hidden=include_hidden,
            )
            return await _build_policy_leaderboard(session, commissioner, pool_name=pool_name)

        if leaderboard_type == "team":
            _, season = await _resolve_season_or_404(session, season_name, allow_hidden=include_hidden)
            return await _build_team_summaries(
                session,
                season_id=season.id,
                pool_name=pool_name,
            )

        _, _, commissioner = await _resolve_team_commissioner_or_400(
            session,
            season_name,
            allow_hidden=include_hidden,
            detail="Score-policies leaderboard is only available for team seasons",
        )
        if pool_name != commissioner.leaderboard_pool:
            raise HTTPException(
                status_code=400,
                detail=f"Score-policies leaderboard must use pool '{commissioner.leaderboard_pool}'",
            )
        return await _build_score_policies_leaderboard(session, commissioner)

    return router
