from __future__ import annotations

import logging
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import col, func, select

# pyright: reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false
# SQLModel Relationship() type annotations cause false positives on join()/selectinload()
from metta.app_backend.database import get_db
from metta.app_backend.models.tournament import (
    Match,
    MatchPlayer,
    MatchStatus,
    Pool,
    PoolPlayer,
    Season,
    Team,
    TeamPolicyVersion,
)
from metta.app_backend.tournament.referees.base import EpisodeTags, MatchCountEntry, MatchRequest
from metta.app_backend.tournament.referees.teams.team_stage import (
    TeamConfig,
    build_pending_team_match_schedule,
)
from metta.app_backend.tournament.settings import MAX_OUTSTANDING_MATCHES_PER_SEASON
from metta.app_backend.tournament.teams.scoring import compute_team_average_scores

logger = logging.getLogger(__name__)


class TeamMembershipChangeRequest(BaseModel):
    pool_name: str
    cog_specs: list[tuple[UUID, int]]
    parent_team_id: UUID | None = None
    notes: str | None = None


class TeamDbHelpersMixin:
    async def _count_in_flight_matches(self, pool_id: UUID) -> int:
        session = get_db()
        unfinished = await session.execute(
            select(func.count())
            .select_from(Match)
            .where(Match.pool_id == pool_id)
            .where(col(Match.status).in_([MatchStatus.pending, MatchStatus.scheduled, MatchStatus.running]))
        )
        return unfinished.scalar_one()

    async def _compute_policy_scores(self, pool_id: UUID) -> dict[UUID, float]:
        session = get_db()
        rows = (
            await session.execute(
                select(
                    PoolPlayer.policy_version_id,
                    func.avg(MatchPlayer.score),
                )
                .join(MatchPlayer, MatchPlayer.pool_player_id == PoolPlayer.id)
                .join(Match, Match.id == MatchPlayer.match_id)
                .where(PoolPlayer.pool_id == pool_id)
                .where(col(PoolPlayer.retired).is_(False))
                .where(Match.status == MatchStatus.completed)
                .where(col(MatchPlayer.score).is_not(None))
                .group_by(PoolPlayer.policy_version_id)
            )
        ).all()
        return {row[0]: float(row[1]) for row in rows if row[1] is not None}

    async def _get_policy_match_counts(self, pool_id: UUID, pool_player_ids: set[UUID]) -> dict[UUID, MatchCountEntry]:
        session = get_db()
        if not pool_player_ids:
            return {}

        result = await session.execute(
            select(MatchPlayer.pool_player_id, Match.status, func.count())
            .join(MatchPlayer.match)
            .where(Match.pool_id == pool_id)
            .where(col(MatchPlayer.pool_player_id).in_(pool_player_ids))
            .group_by(MatchPlayer.pool_player_id, Match.status)
        )

        zero_counts = MatchCountEntry.zero()
        counts: dict[UUID, MatchCountEntry] = {pool_player_id: zero_counts for pool_player_id in pool_player_ids}
        for pool_player_id, status, count in result.all():
            prev = counts.get(pool_player_id, zero_counts)
            if status == MatchStatus.completed:
                counts[pool_player_id] = MatchCountEntry(prev.completed + count, prev.failed, prev.in_progress)
            elif status == MatchStatus.failed:
                counts[pool_player_id] = MatchCountEntry(prev.completed, prev.failed + count, prev.in_progress)
            else:
                counts[pool_player_id] = MatchCountEntry(prev.completed, prev.failed, prev.in_progress + count)
        return counts

    async def _create_team_pool(self, season_id: UUID, pool_name: str) -> Pool:
        session = get_db()
        pool = Pool(season_id=season_id, name=pool_name)
        session.add(pool)
        await session.flush()
        return pool

    async def _copy_pool_players(self, source_pool_id: UUID, target_pool_id: UUID) -> None:
        session = get_db()

        source_players = await self._get_pool_players(source_pool_id)
        existing_result = await session.execute(
            select(PoolPlayer.policy_version_id).where(PoolPlayer.pool_id == target_pool_id)
        )
        existing_ids = {row[0] for row in existing_result.all()}

        for pp in source_players:
            if pp.policy_version_id in existing_ids:
                continue
            session.add(PoolPlayer(pool_id=target_pool_id, policy_version_id=pp.policy_version_id))

        await session.flush()

    async def _apply_team_membership_changes(self, changes: list[TeamMembershipChangeRequest]) -> None:
        if not changes:
            return
        session = get_db()

        pool_names = {c.pool_name for c in changes}
        pools_result = await session.execute(
            select(Pool).join(Pool.season).where(Season.id == self.season_id).where(col(Pool.name).in_(pool_names))
        )
        pools = {p.name: p for p in pools_result.scalars().all() if p.name}

        for change in changes:
            pool = pools[change.pool_name]

            team = Team(pool_id=pool.id)
            session.add(team)

            for pv_id, position in change.cog_specs:
                session.add(
                    TeamPolicyVersion(
                        team=team,
                        policy_version_id=pv_id,
                        position=position,
                    )
                )

            logger.info(f"Created team in pool '{change.pool_name}' with {len(change.cog_specs)} slots")

        await session.commit()

    async def _all_teams_done(self, pool_id: UUID, teams: list[Team], matches_per_team: int) -> bool:
        team_ids = {t.id for t in teams}
        counts = await self._get_team_match_counts(pool_id, team_ids)
        zero_counts = MatchCountEntry.zero()

        for team in teams:
            team_counts = counts.get(team.id, zero_counts)
            if team_counts.in_progress > 0:
                return False
            if team_counts.completed >= matches_per_team:
                continue
            if team_counts.failed >= self.config.max_failed_attempts:
                continue
            return False

        return True

    async def _get_team_match_counts(self, pool_id: UUID, team_ids: set[UUID]) -> dict[UUID, MatchCountEntry]:
        session = get_db()
        if not team_ids:
            return {}

        result = await session.execute(
            select(Match.team_id, Match.status, func.count())
            .where(Match.pool_id == pool_id)
            .where(col(Match.team_id).in_(team_ids))
            .group_by(Match.team_id, Match.status)
        )

        zero_counts = MatchCountEntry.zero()
        counts: dict[UUID, MatchCountEntry] = {team_id: zero_counts for team_id in team_ids}
        for team_id, status, count in result.all():
            if team_id is None:
                continue
            prev = counts.get(team_id, zero_counts)
            if status == MatchStatus.completed:
                counts[team_id] = MatchCountEntry(prev.completed + count, prev.failed, prev.in_progress)
            elif status == MatchStatus.failed:
                counts[team_id] = MatchCountEntry(prev.completed, prev.failed + count, prev.in_progress)
            else:
                counts[team_id] = MatchCountEntry(prev.completed, prev.failed, prev.in_progress + count)
        return counts

    async def _get_teams(self, pool_id: UUID) -> list[Team]:
        session = get_db()
        result = await session.execute(
            select(Team).where(Team.pool_id == pool_id).options(selectinload(Team.policy_versions))
        )
        return list(result.scalars().all())

    async def _get_alive_teams(self, pool_id: UUID) -> list[Team]:
        session = get_db()
        result = await session.execute(
            select(Team)
            .where(Team.pool_id == pool_id, col(Team.eliminated).is_(False))
            .options(selectinload(Team.policy_versions))
        )
        return list(result.scalars().all())

    async def _build_team_configs(self, pool_id: UUID, teams: list[Team]) -> list[TeamConfig]:
        session = get_db()

        pp_result = await session.execute(
            select(PoolPlayer).where(PoolPlayer.pool_id == pool_id, col(PoolPlayer.retired).is_(False))
        )
        pool_players = list(pp_result.scalars().all())
        pp_by_pv: dict[UUID, UUID] = {pp.policy_version_id: pp.id for pp in pool_players}

        configs: list[TeamConfig] = []
        for team in teams:
            sorted_slots = sorted(team.policy_versions, key=lambda tpv: tpv.position)
            pv_ids = [tpv.policy_version_id for tpv in sorted_slots]
            unique_pvs = list(dict.fromkeys(pv_ids))

            if any(pv not in pp_by_pv for pv in unique_pvs):
                continue

            pv_to_idx = {pv: i for i, pv in enumerate(unique_pvs)}

            assignments = [pv_to_idx[pv] for pv in pv_ids]
            pool_player_ids = [pp_by_pv[pv] for pv in unique_pvs]

            configs.append(TeamConfig(team_id=team.id, pool_player_ids=pool_player_ids, assignments=assignments))

        return configs

    async def _schedule_team_eval_matches(
        self,
        season,
        pool: Pool,
        teams: list[TeamConfig],
        matches_per_team: int,
    ) -> int:
        if not teams:
            return 0

        team_counts = await self._get_team_match_counts(pool.id, {team.team_id for team in teams})
        zero_counts = MatchCountEntry.zero()
        outstanding = await self._count_outstanding_matches()
        slots = max(0, MAX_OUTSTANDING_MATCHES_PER_SEASON - outstanding)
        if slots <= 0:
            return 0

        pending = build_pending_team_match_schedule(
            teams,
            matches_per_team=matches_per_team,
            get_counts=lambda team: team_counts.get(team.team_id, zero_counts),
            max_failed_attempts=self.config.max_failed_attempts,
            limit=slots,
        )
        if not pending:
            return 0

        seed = 42
        self._require_pool_env_config(pool)
        scheduled = 0
        for team, seed_offset in pending:
            request = MatchRequest(
                pool_player_ids=team.pool_player_ids,
                assignments=team.assignments,
                map_seed=seed + seed_offset,
                episode_tags=EpisodeTags(match_type="team_elimination", team_id=team.team_id),
                seed=seed,
                team_id=team.team_id,
            )
            if await self._create_and_dispatch_match(pool, request):
                scheduled += 1

        return scheduled

    async def _compute_team_scores(self, pool_id: UUID, team_ids: set[UUID]) -> dict[UUID, float]:
        session = get_db()
        return await compute_team_average_scores(
            session,
            pool_id=pool_id,
            team_ids=team_ids,
        )
