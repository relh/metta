from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

# pyright: reportArgumentType=false, reportCallIssue=false
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from metta.app_backend.models.tournament import Match, MatchStatus, Pool, PoolPlayer, Team
from metta.app_backend.tournament.progress import StageStats


@dataclass(frozen=True)
class StageStatsCounts:
    policy_counts: dict[UUID, int]
    match_status_counts: dict[UUID, dict[MatchStatus, int]]
    team_counts: dict[UUID, int]
    eliminated_counts: dict[UUID, int]


async def load_stage_stats_counts(
    session: AsyncSession,
    pool_ids: set[UUID],
    *,
    include_retired_policies: bool,
) -> StageStatsCounts:
    if not pool_ids:
        return StageStatsCounts(
            policy_counts={},
            match_status_counts={},
            team_counts={},
            eliminated_counts={},
        )

    policy_query = (
        select(PoolPlayer.pool_id, func.count())
        .where(col(PoolPlayer.pool_id).in_(pool_ids))
        .group_by(PoolPlayer.pool_id)
    )
    if not include_retired_policies:
        policy_query = policy_query.where(col(PoolPlayer.retired).is_(False))
    policy_count_rows = await session.execute(policy_query)
    policy_counts = {pool_id: count for pool_id, count in policy_count_rows.all()}

    match_status_rows = await session.execute(
        select(Match.pool_id, Match.status, func.count())
        .where(col(Match.pool_id).in_(pool_ids))
        .group_by(Match.pool_id, Match.status)
    )
    match_status_counts: dict[UUID, dict[MatchStatus, int]] = {}
    for pool_id, status, count in match_status_rows.all():
        if pool_id is None:
            continue
        status_counts = match_status_counts.setdefault(pool_id, {})
        status_counts[status] = count

    team_count_rows = await session.execute(
        select(
            Team.pool_id,
            func.count(),
            func.count().filter(col(Team.eliminated).is_(True)),
        )
        .where(col(Team.pool_id).in_(pool_ids))
        .group_by(Team.pool_id)
    )
    team_counts: dict[UUID, int] = {}
    eliminated_counts: dict[UUID, int] = {}
    for pool_id, team_count, eliminated_count in team_count_rows.all():
        team_counts[pool_id] = team_count
        eliminated_counts[pool_id] = eliminated_count

    return StageStatsCounts(
        policy_counts=policy_counts,
        match_status_counts=match_status_counts,
        team_counts=team_counts,
        eliminated_counts=eliminated_counts,
    )


def build_stage_stats_row(pool_name: str, pool: Pool | None, counts: StageStatsCounts) -> StageStats:
    if pool is None:
        return StageStats(name=pool_name, policy_count=0, match_count=0, completion_pct=0.0)

    status_counts = counts.match_status_counts.get(pool.id, {})
    total_matches = sum(status_counts.values())
    completed = status_counts.get(MatchStatus.completed, 0)
    kwargs: dict[str, Any] = {}
    team_count = counts.team_counts.get(pool.id, 0)
    if team_count > 0:
        kwargs["team_count"] = team_count
        kwargs["eliminated_count"] = counts.eliminated_counts.get(pool.id, 0)

    return StageStats(
        name=pool.name,
        policy_count=counts.policy_counts.get(pool.id, 0),
        match_count=total_matches,
        completion_pct=(completed / total_matches * 100) if total_matches > 0 else 0.0,
        **kwargs,
    )
