from __future__ import annotations

from uuid import UUID

from metta_alo.scoring import Scorer
from sqlmodel import col, select

# pyright: reportArgumentType=false, reportCallIssue=false
from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, PoolPlayer
from metta.app_backend.tournament.referees.base import (
    LeaderboardStatsRow,
    ScoredMatchData,
    compute_weighted_score_stddev,
)
from metta.app_backend.tournament.referees.leaderboard_rows import group_match_rows


class MockLeaderboardMixin:
    """Leaderboard helper for mock tournaments that do not emit episode rows."""

    scorer: Scorer

    async def get_leaderboard_with_stats(self, pool_id: UUID) -> list[LeaderboardStatsRow]:
        from metta.app_backend.database import get_db  # noqa: PLC0415

        session = get_db()
        rows = (
            await session.execute(
                select(
                    col(Match.id).label("match_id"),
                    Match.assignments,
                    MatchPlayer.policy_index,
                    MatchPlayer.score,
                    PoolPlayer.policy_version_id,
                )
                .select_from(Match)
                .join(Match.players)
                .join(MatchPlayer.pool_player)
                .where(Match.pool_id == pool_id)
                .where(Match.status == MatchStatus.completed)
            )
        ).all()

        if not rows:
            return []

        match_data = group_match_rows(rows)

        all_policy_ids: set[UUID] = set()
        match_counts: dict[UUID, int] = {}
        scored_matches: list[ScoredMatchData] = []

        for match_id, match_entry in match_data.items():
            players = match_entry.players
            if not players or any(score is None for _, score, _ in players):
                continue

            assignment_counts: dict[int, int] = {}
            for policy_index in match_entry.assignments:
                assignment_counts[policy_index] = assignment_counts.get(policy_index, 0) + 1

            policy_scores: dict[UUID, float] = {}
            policy_version_ids: list[UUID] = []
            policy_agent_counts: dict[UUID, int] = {}

            for policy_index, score, policy_version_id in sorted(players, key=lambda entry: entry[0]):
                policy_scores[policy_version_id] = score
                if policy_index >= len(policy_version_ids):
                    policy_version_ids.append(policy_version_id)
                policy_agent_counts[policy_version_id] = policy_agent_counts.get(
                    policy_version_id, 0
                ) + assignment_counts.get(policy_index, 0)
                all_policy_ids.add(policy_version_id)
                match_counts[policy_version_id] = match_counts.get(policy_version_id, 0) + 1

            if sum(policy_agent_counts.values()) == 0:
                continue

            scored_matches.append(
                ScoredMatchData(
                    match_id=match_id,
                    policy_scores=policy_scores,
                    assignments=match_entry.assignments,
                    policy_version_ids=policy_version_ids,
                    policy_agent_counts=policy_agent_counts,
                )
            )

        if not scored_matches:
            return []

        scores = self.scorer.compute_scores(list(all_policy_ids), scored_matches)
        score_stddevs = compute_weighted_score_stddev(scores, scored_matches)
        return sorted(
            (
                LeaderboardStatsRow(
                    policy_version_id=pv_id,
                    score=score,
                    match_count=match_counts.get(pv_id, 0),
                    score_stddev=score_stddevs.get(pv_id),
                )
                for pv_id, score in scores.items()
            ),
            key=lambda row: row.score,
            reverse=True,
        )
