from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import col, select

# pyright: reportArgumentType=false, reportCallIssue=false
# SQLModel Relationship() type annotations cause false positives on join()/selectinload()
from metta.app_backend.database import get_db
from metta.app_backend.models.tournament import Pool, PoolPlayer, Team
from metta.app_backend.tournament.referees.base import MatchCounts, MatchRequest, RefereeBase
from metta.app_backend.tournament.teams.scoring import (
    compute_policy_placement_scores,
    compute_team_average_scores,
    rank_teams_by_score,
)
from mettagrid.config.mettagrid_config import MettaGridConfig


class ScoreStageReferee(RefereeBase):
    description: str

    def __init__(self, *, source_team_pool_name: str, top_k: int) -> None:
        self.source_team_pool_name = source_team_pool_name
        self.top_k = top_k
        self.description = f"Policy scores derived from top {top_k} team placements"

    def make_env(self, seed: int) -> MettaGridConfig:  # pragma: no cover
        raise RuntimeError("ScoreStageReferee does not schedule matches")

    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
        limit: int = 0,
    ) -> list[MatchRequest]:  # type: ignore[unused-arg]
        return []

    async def _get_policy_placement_leaderboard(self, pool_id: UUID) -> list[tuple[UUID, float, list[int]]]:
        session = get_db()

        output_pool = (await session.execute(select(Pool).where(Pool.id == pool_id))).scalar_one()
        source_pool = (
            await session.execute(
                select(Pool)
                .where(Pool.season_id == output_pool.season_id)
                .where(Pool.name == self.source_team_pool_name)
            )
        ).scalar_one_or_none()
        if source_pool is None:
            return []

        teams_result = await session.execute(
            select(Team).where(Team.pool_id == source_pool.id).options(selectinload(Team.policy_versions))
        )
        teams = list(teams_result.scalars().all())
        if not teams:
            return []

        team_scores = await compute_team_average_scores(
            session,
            pool_id=source_pool.id,
            team_ids={team.id for team in teams},
        )
        ranked = rank_teams_by_score(teams, team_scores)

        pool_player_rows = await session.execute(
            select(PoolPlayer.policy_version_id)
            .where(PoolPlayer.pool_id == pool_id)
            .where(col(PoolPlayer.retired).is_(False))
        )
        output_policy_ids = [row[0] for row in pool_player_rows.all()]

        placement_scores = compute_policy_placement_scores(
            ranked,
            top_k=self.top_k,
            policy_ids=output_policy_ids,
        )
        leaderboard = [(pv_id, placement_scores[pv_id][0], placement_scores[pv_id][1]) for pv_id in output_policy_ids]

        return sorted(leaderboard, key=lambda row: row[1])

    async def get_leaderboard(self, pool_id: UUID) -> list[tuple[UUID, float, int]]:
        leaderboard = await self._get_policy_placement_leaderboard(pool_id)
        return [(pv_id, score, len(team_ranks)) for pv_id, score, team_ranks in leaderboard]

    async def get_leaderboard_with_team_ranks(self, pool_id: UUID) -> list[tuple[UUID, float, list[int]]]:
        return await self._get_policy_placement_leaderboard(pool_id)
