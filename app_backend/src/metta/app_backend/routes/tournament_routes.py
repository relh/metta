from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

# pyright: reportArgumentType=false
# SQLModel's Relationship() returns the target type, not SQLAlchemy's InstrumentedAttribute,
# causing false positives on join() and selectinload() calls.
from metta.app_backend.auth import CheckMaybeUser, CheckUser
from metta.app_backend.database import db_session
from metta.app_backend.models.job_request import JobRequest
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import (
    Match,
    MatchPlayer,
    MatchStatus,
    MembershipChange,
    Pool,
    PoolPlayer,
    Season,
)
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.routes.docs_routes import public_api
from metta.app_backend.tournament.registry import SEASONS
from metta.app_backend.tournament.season_resolver import get_season_versions, parse_season_ref, resolve_season
from metta.app_backend.tournament.settings import DEFAULT_SEASON, HIDDEN_SEASONS


async def get_session():
    async with db_session() as session:
        yield session


class PolicyVersionSummary(BaseModel):
    id: UUID
    name: str | None
    version: int | None

    @classmethod
    def from_model(cls, pv: PolicyVersion) -> "PolicyVersionSummary":
        return cls(id=pv.id, name=pv.policy.name, version=pv.version)


class LeaderboardEntry(BaseModel):
    rank: int
    policy: PolicyVersionSummary
    score: float
    matches: int


class PoolMembership(BaseModel):
    pool_name: str
    active: bool
    completed: int
    failed: int
    pending: int


class PolicySummary(BaseModel):
    policy: PolicyVersionSummary
    pools: list[PoolMembership]
    entered_at: str


class SubmitRequest(BaseModel):
    policy_version_id: UUID


class SubmitResponse(BaseModel):
    pools: list[str]


class MatchPlayerSummary(BaseModel):
    policy: PolicyVersionSummary
    policy_index: int
    score: float | None


class MatchSummary(BaseModel):
    id: UUID
    pool_name: str
    status: str
    assignments: list[int]
    players: list[MatchPlayerSummary]
    job_id: UUID | None
    episode_id: str | None
    created_at: str


class MembershipHistoryEntry(BaseModel):
    season_name: str
    season_version: int | None
    pool_name: str
    action: str
    notes: str | None
    created_at: str


class PoolInfo(BaseModel):
    id: UUID | None = None
    name: str
    description: str
    config_id: UUID | None = None


class SeasonVersionInfo(BaseModel):
    version: int
    canonical: bool
    disabled_at: str | None
    created_at: str


class SeasonResponse(BaseModel):
    id: UUID
    name: str
    version: int
    canonical: bool
    summary: str
    entry_pool: str | None = None
    leaderboard_pool: str | None = None
    is_default: bool
    pools: list[PoolInfo]

    @classmethod
    def from_commissioner(
        cls,
        season_id: UUID,
        season_name: str,
        version: int = 1,
        canonical: bool = True,
        pools_by_name: dict[str, Pool] | None = None,
    ) -> "SeasonResponse":
        if season_name not in SEASONS:
            return cls(
                id=season_id,
                name=season_name,
                version=version,
                canonical=canonical,
                summary="",
                pools=[],
                is_default=False,
            )
        commissioner = SEASONS[season_name]()
        desc = commissioner.description_for_version(version)
        db_pools = pools_by_name or {}
        return cls(
            id=season_id,
            name=season_name,
            version=version,
            canonical=canonical,
            summary=desc.summary,
            entry_pool=commissioner.entry_pool,
            leaderboard_pool=commissioner.leaderboard_pool,
            is_default=season_name == DEFAULT_SEASON,
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


async def _get_pools_by_name(session: AsyncSession, season_id: UUID) -> dict[str, Pool]:
    pools = (await session.execute(select(Pool).where(Pool.season_id == season_id))).scalars().all()
    return {p.name: p for p in pools if p.name}


@public_api
def create_tournament_router() -> APIRouter:
    router = APIRouter(prefix="/tournament", tags=["tournament"])

    @router.get("/seasons")
    @timed_http_handler
    async def list_seasons(session: AsyncSession = Depends(get_session)) -> list[SeasonResponse]:
        seasons = (
            (
                await session.execute(
                    select(Season).where(col(Season.name).not_in(HIDDEN_SEASONS), col(Season.canonical).is_(True))
                )
            )
            .scalars()
            .all()
        )

        results = []
        for s in seasons:
            pools_by_name = await _get_pools_by_name(session, s.id)
            results.append(SeasonResponse.from_commissioner(s.id, s.name, s.version, s.canonical, pools_by_name))
        return results

    @router.get("/seasons/{season_name}")
    @timed_http_handler
    async def get_season(season_name: str, session: AsyncSession = Depends(get_session)) -> SeasonResponse:
        name, version = parse_season_ref(season_name)
        if name not in SEASONS or name in HIDDEN_SEASONS:
            raise HTTPException(status_code=404, detail="Season not found")

        season = await resolve_season(session, name, version)
        if not season:
            raise HTTPException(status_code=404, detail="Season version not found")

        pools_by_name = await _get_pools_by_name(session, season.id)
        return SeasonResponse.from_commissioner(season.id, name, season.version, season.canonical, pools_by_name)

    @router.get("/seasons/{season_name}/pools/{pool_name}/config")
    @timed_http_handler
    async def get_pool_config(
        season_name: str, pool_name: str, session: AsyncSession = Depends(get_session)
    ) -> JSONResponse:
        name, version = parse_season_ref(season_name)
        if name not in SEASONS or name in HIDDEN_SEASONS:
            raise HTTPException(status_code=404, detail="Season not found")

        season = await resolve_season(session, name, version)
        if not season:
            raise HTTPException(status_code=404, detail="Season version not found")

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
    async def get_config(config_id: UUID, session: AsyncSession = Depends(get_session)) -> JSONResponse:
        from metta.app_backend.models.tournament import MettagridEnvConfig  # noqa: PLC0415

        env_config = (await session.execute(select(MettagridEnvConfig).filter_by(id=config_id))).scalar_one_or_none()
        if not env_config:
            raise HTTPException(status_code=404, detail="Config not found")
        return JSONResponse(content=env_config.config)

    @router.get("/seasons/{season_name}/versions")
    @timed_http_handler
    async def list_season_versions(
        season_name: str,
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
            )
            for s in versions
        ]

    @router.get("/seasons/{season_name}/leaderboard")
    @timed_http_handler
    async def get_leaderboard(
        season_name: str,
        session: AsyncSession = Depends(get_session),
        include_hidden: bool = Query(default=False, description="Include leaderboard of a hidden season (for testing)"),
    ) -> list[LeaderboardEntry]:
        name, version = parse_season_ref(season_name)

        if name not in SEASONS or (name in HIDDEN_SEASONS and not include_hidden):
            raise HTTPException(status_code=404, detail="Season not found")

        season = await resolve_season(session, name, version)
        if not season:
            raise HTTPException(status_code=404, detail="Season version not found")

        commissioner = SEASONS[name]()
        leaderboard = await commissioner.get_leaderboard(season_id=season.id)
        if not leaderboard:
            return []

        pv_ids = [pv_id for pv_id, _, _ in leaderboard]
        pvs_result = (
            (
                await session.execute(
                    select(PolicyVersion)
                    .where(col(PolicyVersion.id).in_(pv_ids))
                    .options(selectinload(PolicyVersion.policy))
                )
            )
            .scalars()
            .all()
        )
        pvs = {pv.id: pv for pv in pvs_result}

        return [
            LeaderboardEntry(
                rank=i + 1,
                policy=PolicyVersionSummary.from_model(pvs[pv_id])
                if pv_id in pvs
                else PolicyVersionSummary(id=pv_id, name=None, version=None),
                score=score,
                matches=match_count,
            )
            for i, (pv_id, score, match_count) in enumerate(leaderboard)
        ]

    @router.get("/seasons/{season_name}/policies")
    @timed_http_handler
    async def get_policies(
        season_name: str,
        user: CheckMaybeUser,
        session: AsyncSession = Depends(get_session),
        mine: bool = Query(default=False, description="Filter to only policies owned by the authenticated user"),
        include_hidden: bool = Query(
            default=False, description="Include policies that are part of a hidden season (for testing)"
        ),
    ) -> list[PolicySummary]:
        name, version = parse_season_ref(season_name)
        if name not in SEASONS or (name in HIDDEN_SEASONS and not include_hidden):
            raise HTTPException(status_code=404, detail="Season not found")

        season = await resolve_season(session, name, version)
        if not season:
            raise HTTPException(status_code=404, detail="Season version not found")

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

    @router.get("/seasons/{season_name}/matches")
    @timed_http_handler
    async def get_matches(
        season_name: str,
        session: AsyncSession = Depends(get_session),
        limit: int = 50,
        offset: int = 0,
        pool_names: list[str] | None = Query(default=None),
        policy_version_ids: list[UUID] | None = Query(default=None),
    ) -> list[MatchSummary]:
        name, version = parse_season_ref(season_name)
        if name not in SEASONS or name in HIDDEN_SEASONS:
            raise HTTPException(status_code=404, detail="Season not found")

        season = await resolve_season(session, name, version)
        if not season:
            raise HTTPException(status_code=404, detail="Season version not found")

        query = select(Match, JobRequest.episode_id).join(Match.job).join(Match.pool).where(Pool.season_id == season.id)

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
                selectinload(Match.players)
                .selectinload(MatchPlayer.pool_player)
                .selectinload(PoolPlayer.policy_version)
                .selectinload(PolicyVersion.policy),
                selectinload(Match.pool),
            )
        )

        rows = (await session.execute(query)).all()
        if not rows:
            return []

        return [
            MatchSummary(
                id=m.id,
                pool_name=m.pool.name,
                status=m.status.value,
                assignments=m.assignments or [],
                players=[
                    MatchPlayerSummary(
                        policy=PolicyVersionSummary.from_model(mp.pool_player.policy_version),
                        policy_index=mp.policy_index,
                        score=mp.score,
                    )
                    for mp in sorted(m.players, key=lambda p: p.policy_index)
                ],
                job_id=m.job_id,
                episode_id=episode_id,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
            for m, episode_id in rows
        ]

    @router.post("/seasons/{season_name}/submissions")
    @timed_http_handler
    async def submit_policy(
        season_name: str, request: SubmitRequest, _user: CheckUser, session: AsyncSession = Depends(get_session)
    ) -> SubmitResponse:
        name, version = parse_season_ref(season_name)
        if name not in SEASONS:
            raise HTTPException(status_code=404, detail="Season not found")
        if version is not None:
            raise HTTPException(status_code=400, detail="Submitting to a season version is not supported")

        season = await resolve_season(session, name, version)
        if not season:
            raise HTTPException(status_code=404, detail="Season version not found")

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

        commissioner = SEASONS[name]()
        pool_names = await commissioner.submit(request.policy_version_id)
        return SubmitResponse(pools=pool_names)

    @router.get("/policies/{policy_version_id}/memberships")
    @timed_http_handler
    async def get_policy_memberships(
        policy_version_id: UUID, session: AsyncSession = Depends(get_session)
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
    async def get_my_memberships(user: CheckUser, session: AsyncSession = Depends(get_session)) -> dict[str, list[str]]:
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

    return router
