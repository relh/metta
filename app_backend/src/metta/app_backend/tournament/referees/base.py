import math
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import NamedTuple
from uuid import UUID

from metta_alo.scoring import Scorer, WeightedScorer
from pydantic import BaseModel, Field
from sqlmodel import col, select

# pyright: reportArgumentType=false
from metta.app_backend.models.episodes import EpisodePolicy
from metta.app_backend.models.job_request import JobRequest
from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, PoolPlayer
from metta.app_backend.tournament.referees.envs import GameEnvGenerator
from metta.app_backend.tournament.referees.leaderboard_rows import group_match_rows
from mettagrid.config.mettagrid_config import MettaGridConfig

# -- Match counts --


class MatchCountEntry(NamedTuple):
    completed: int
    failed: int
    in_progress: int

    @classmethod
    def zero(cls) -> "MatchCountEntry":
        return cls(completed=0, failed=0, in_progress=0)


MatchCountKey = tuple[tuple[UUID, ...], tuple[int, ...]]
MatchCounts = dict[MatchCountKey, MatchCountEntry]


class EpisodeTags(BaseModel):
    match_type: str
    team_size: int | None = None
    team_id: UUID | None = None
    game: str | None = None
    assignments: str | None = None


class MatchRequest(BaseModel):
    pool_player_ids: list[UUID]
    assignments: list[int]
    map_seed: int
    episode_tags: EpisodeTags
    seed: int
    team_id: UUID | None = None


class ScoredMatchData(BaseModel):
    match_id: UUID
    policy_scores: dict[UUID, float]
    assignments: list[int]
    policy_version_ids: list[UUID]
    policy_agent_counts: dict[UUID, int]
    episode_tags: EpisodeTags | None = None


class LeaderboardStatsRow(BaseModel):
    policy_version_id: UUID
    score: float
    match_count: int
    score_stddev: float | None = None
    score_percentiles: dict[int, float] = Field(default_factory=dict)


def compute_weighted_score_stddev(
    policy_scores: dict[UUID, float],
    scored_matches: list[ScoredMatchData],
) -> dict[UUID, float | None]:
    weighted_sq_error_sums: dict[UUID, float] = defaultdict(float)
    weight_totals: dict[UUID, float] = defaultdict(float)

    for match in scored_matches:
        total_agents = sum(match.policy_agent_counts.values())
        if total_agents <= 0:
            continue

        for policy_version_id, score in match.policy_scores.items():
            if policy_version_id not in policy_scores:
                continue
            agent_count = match.policy_agent_counts.get(policy_version_id, 0)
            if agent_count <= 0:
                continue
            weight = agent_count / total_agents
            error = score - policy_scores[policy_version_id]
            weighted_sq_error_sums[policy_version_id] += error * error * weight
            weight_totals[policy_version_id] += weight

    stddev_by_policy: dict[UUID, float | None] = {}
    for policy_version_id in policy_scores:
        total_weight = weight_totals.get(policy_version_id, 0.0)
        if total_weight <= 0:
            stddev_by_policy[policy_version_id] = None
            continue
        variance = weighted_sq_error_sums.get(policy_version_id, 0.0) / total_weight
        stddev_by_policy[policy_version_id] = math.sqrt(max(variance, 0.0))

    return stddev_by_policy


def _weighted_percentile(
    values_with_weights: list[tuple[float, float]],
    percentile: float,
) -> float | None:
    if not values_with_weights:
        return None

    sorted_values = sorted(values_with_weights, key=lambda item: item[0])
    total_weight = sum(max(weight, 0.0) for _, weight in sorted_values)
    if total_weight <= 0:
        return None

    clamped = min(max(percentile, 0.0), 100.0)
    threshold = (clamped / 100.0) * total_weight
    cumulative = 0.0
    for value, weight in sorted_values:
        cumulative += max(weight, 0.0)
        if cumulative >= threshold:
            return value
    return sorted_values[-1][0]


def compute_weighted_score_percentiles(
    policy_scores: dict[UUID, float],
    scored_matches: list[ScoredMatchData],
    *,
    percentiles: tuple[float, ...] = (30.0, 60.0, 90.0),
) -> dict[UUID, dict[int, float | None]]:
    weighted_scores: dict[UUID, list[tuple[float, float]]] = defaultdict(list)

    for match in scored_matches:
        total_agents = sum(match.policy_agent_counts.values())
        if total_agents <= 0:
            continue

        for policy_version_id, score in match.policy_scores.items():
            if policy_version_id not in policy_scores:
                continue
            agent_count = match.policy_agent_counts.get(policy_version_id, 0)
            if agent_count <= 0:
                continue
            weight = agent_count / total_agents
            weighted_scores[policy_version_id].append((score, weight))

    percentiles_by_policy: dict[UUID, dict[int, float | None]] = {}
    for policy_version_id in policy_scores:
        values = weighted_scores.get(policy_version_id, [])
        percentiles_by_policy[policy_version_id] = {
            int(percentile): _weighted_percentile(values, percentile) for percentile in percentiles
        }
    return percentiles_by_policy


class RefereeBase(ABC):
    description: str = ""
    env_name: str = ""
    num_agents: int | None = None
    game: GameEnvGenerator | None = None
    scorer: Scorer = WeightedScorer()

    @abstractmethod
    def make_env(self, seed: int) -> MettaGridConfig:
        pass

    @abstractmethod
    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
        limit: int = 0,
    ) -> list[MatchRequest]:
        pass

    async def get_leaderboard(self, pool_id: UUID) -> list[tuple[UUID, float, int]]:
        """Returns list of (policy_version_id, score, match_count) sorted by score descending."""
        return [
            (row.policy_version_id, row.score, row.match_count)
            for row in await self.get_leaderboard_with_stats(pool_id)
        ]

    async def get_leaderboard_with_stats(self, pool_id: UUID) -> list[LeaderboardStatsRow]:
        """Returns rows with mean score, match count, and score stddev."""
        from metta.app_backend.database import get_db  # noqa: PLC0415

        session = get_db()

        # Single flat query replaces 4 separate ORM queries (match + 3 selectinloads).
        # Uses the composite index idx_matches_pool_status on (pool_id, status).
        rows = (
            await session.execute(
                select(
                    col(Match.id).label("match_id"),
                    Match.assignments,
                    MatchPlayer.policy_index,
                    MatchPlayer.score,
                    PoolPlayer.policy_version_id,
                    JobRequest.result["episode_id"].astext.label("episode_id"),  # type: ignore[index]
                )
                .select_from(Match)
                .join(Match.job)
                .join(Match.players)
                .join(MatchPlayer.pool_player)
                .where(Match.pool_id == pool_id)
                .where(Match.status == MatchStatus.completed)
                .where(JobRequest.episode_id.is_not(None))
            )
        ).all()

        if not rows:
            return []

        match_data = group_match_rows(rows, include_episode_id=True)

        # Collect episode IDs for agent count lookup
        episode_ids = [md.episode_id for md in match_data.values() if md.episode_id is not None]

        # Fetch agent counts — query EpisodePolicy directly, no need to join Episode table
        agent_counts_by_episode: dict[UUID, dict[UUID, int]] = defaultdict(dict)
        if episode_ids:
            counts_result = await session.execute(
                select(
                    EpisodePolicy.episode_id,
                    EpisodePolicy.policy_version_id,
                    EpisodePolicy.num_agents,
                ).where(col(EpisodePolicy.episode_id).in_(episode_ids))
            )
            for ep_id, pv_id, num_agents in counts_result.all():
                agent_counts_by_episode[ep_id][pv_id] = num_agents

        # Build scored matches
        all_policy_ids: set[UUID] = set()
        match_counts: dict[UUID, int] = {}
        scored_matches: list[ScoredMatchData] = []

        for mid, md in match_data.items():
            if not md.players or any(score is None for _, score, _ in md.players):
                continue

            if md.episode_id is None:
                continue
            episode_agent_counts = agent_counts_by_episode.get(md.episode_id)
            if not episode_agent_counts:
                continue

            policy_scores: dict[UUID, float] = {}
            policy_version_ids: list[UUID] = []
            for policy_index, score, pv_id in sorted(md.players, key=lambda x: x[0]):
                policy_scores[pv_id] = score
                if policy_index >= len(policy_version_ids):
                    policy_version_ids.append(pv_id)
                all_policy_ids.add(pv_id)
                match_counts[pv_id] = match_counts.get(pv_id, 0) + 1

            scored_matches.append(
                ScoredMatchData(
                    match_id=mid,
                    policy_scores=policy_scores,
                    assignments=md.assignments,
                    policy_version_ids=policy_version_ids,
                    policy_agent_counts=episode_agent_counts,
                )
            )

        if not scored_matches:
            return []

        scores = self.scorer.compute_scores(list(all_policy_ids), scored_matches)
        score_stddevs = compute_weighted_score_stddev(scores, scored_matches)
        score_percentiles = compute_weighted_score_percentiles(scores, scored_matches)
        results = [
            LeaderboardStatsRow(
                policy_version_id=policy_version_id,
                score=score,
                match_count=match_counts.get(policy_version_id, 0),
                score_stddev=score_stddevs.get(policy_version_id),
                score_percentiles={
                    k: v for k, v in score_percentiles.get(policy_version_id, {}).items() if v is not None
                },
            )
            for policy_version_id, score in scores.items()
        ]
        return sorted(results, key=lambda row: row.score, reverse=True)
