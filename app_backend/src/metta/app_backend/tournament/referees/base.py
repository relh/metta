from abc import ABC, abstractmethod
from collections import defaultdict
from uuid import UUID

from metta_alo.scoring import Scorer, WeightedScorer
from pydantic import BaseModel
from sqlmodel import col, select

# pyright: reportArgumentType=false
from metta.app_backend.models.episodes import EpisodePolicy
from metta.app_backend.models.job_request import JobRequest
from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, PoolPlayer
from mettagrid.config.mettagrid_config import MettaGridConfig

MatchCountKey = tuple[tuple[UUID, ...], tuple[int, ...]]
MatchCounts = dict[MatchCountKey, tuple[int, int, int]]


class MatchRequest(BaseModel):
    pool_player_ids: list[UUID]
    assignments: list[int]
    env: MettaGridConfig
    episode_tags: dict[str, str] = {}
    seed: int


class ScoredMatchData(BaseModel):
    match_id: UUID
    policy_scores: dict[UUID, float]
    assignments: list[int]
    policy_version_ids: list[UUID]
    policy_agent_counts: dict[UUID, int]
    episode_tags: dict[str, str] = {}


class RefereeBase(ABC):
    description: str = ""
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

        # Group flat rows by match_id
        match_data: dict[UUID, dict] = {}
        for row in rows:
            mid = row.match_id
            if mid not in match_data:
                match_data[mid] = {
                    "assignments": row.assignments,
                    "episode_id": row.episode_id,
                    "players": [],
                }
            match_data[mid]["players"].append((row.policy_index, row.score, row.policy_version_id))

        # Collect episode IDs for agent count lookup
        episode_ids: list[UUID] = []
        for md in match_data.values():
            if md["episode_id"]:
                episode_ids.append(UUID(md["episode_id"]))

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
            if not md["players"] or any(score is None for _, score, _ in md["players"]):
                continue

            episode_id = UUID(md["episode_id"])
            episode_agent_counts = agent_counts_by_episode.get(episode_id)
            if not episode_agent_counts:
                continue

            policy_scores: dict[UUID, float] = {}
            policy_version_ids: list[UUID] = []
            for policy_index, score, pv_id in sorted(md["players"], key=lambda x: x[0]):
                policy_scores[pv_id] = score
                if policy_index >= len(policy_version_ids):
                    policy_version_ids.append(pv_id)
                all_policy_ids.add(pv_id)
                match_counts[pv_id] = match_counts.get(pv_id, 0) + 1

            scored_matches.append(
                ScoredMatchData(
                    match_id=mid,
                    policy_scores=policy_scores,
                    assignments=md["assignments"],
                    policy_version_ids=policy_version_ids,
                    policy_agent_counts=episode_agent_counts,
                )
            )

        if not scored_matches:
            return []

        scores = self.scorer.compute_scores(list(all_policy_ids), scored_matches)
        results = [(pv, score, match_counts.get(pv, 0)) for pv, score in scores.items()]
        return sorted(results, key=lambda x: x[1], reverse=True)
