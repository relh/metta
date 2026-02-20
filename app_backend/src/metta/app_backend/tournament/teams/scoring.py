from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from uuid import UUID

# pyright: reportArgumentType=false, reportCallIssue=false
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, Team


async def compute_team_average_scores(
    session: AsyncSession,
    *,
    pool_id: UUID,
    team_ids: Iterable[UUID],
) -> dict[UUID, float]:
    ids = set(team_ids)
    if not ids:
        return {}

    score_rows = await session.execute(
        select(Match.team_id, func.avg(MatchPlayer.score))
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(Match.pool_id == pool_id)
        .where(Match.status == MatchStatus.completed)
        .where(col(Match.team_id).in_(ids))
        .group_by(Match.team_id)
    )
    return {team_id: float(score) for team_id, score in score_rows.all() if team_id is not None and score is not None}


def rank_teams_by_score(
    teams: Sequence[Team],
    team_scores: dict[UUID, float],
    *,
    missing_score: float = float("-inf"),
    require_score: bool = False,
) -> list[Team]:
    if require_score:
        return sorted(teams, key=lambda team: team_scores[team.id], reverse=True)
    return sorted(teams, key=lambda team: team_scores.get(team.id, missing_score), reverse=True)


def compute_policy_placement_scores(
    ranked_teams: Sequence[Team],
    *,
    top_k: int,
    policy_ids: Iterable[UUID] | None = None,
) -> dict[UUID, tuple[float, list[int]]]:
    positions_by_policy: dict[UUID, list[int]] = defaultdict(list)
    for position, team in enumerate(ranked_teams, start=1):
        for policy_version_id in {tpv.policy_version_id for tpv in team.policy_versions}:
            positions_by_policy[policy_version_id].append(position)

    target_policy_ids = list(policy_ids) if policy_ids is not None else list(positions_by_policy.keys())
    penalty_position = len(ranked_teams) + 1
    results: dict[UUID, tuple[float, list[int]]] = {}
    for policy_version_id in target_policy_ids:
        positions = sorted(positions_by_policy.get(policy_version_id, []))
        top_positions = positions[:top_k]
        while len(top_positions) < top_k:
            top_positions.append(penalty_position)
        results[policy_version_id] = (float(sum(top_positions)), positions)

    return results
