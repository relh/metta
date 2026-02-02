from abc import ABC, abstractmethod
from collections import defaultdict
from uuid import UUID

from metta_alo.scoring import Scorer, WeightedScorer
from pydantic import BaseModel
from sqlmodel import col, select

# pyright: reportArgumentType=false
from metta.app_backend.models.episodes import Episode, EpisodePolicy
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
    # Temporarily disable replays for games where mettascope doesn't support the new config format
    skip_replay: bool = False


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
        from sqlalchemy.orm import selectinload

        from metta.app_backend.database import get_db

        session = get_db()
        matches = list(
            (
                await session.execute(
                    select(Match)
                    .join(Match.job)
                    .where(Match.pool_id == pool_id)
                    .where(Match.status == MatchStatus.completed)
                    .where(JobRequest.episode_id.is_not(None))
                    .options(
                        selectinload(Match.players).selectinload(MatchPlayer.pool_player),
                        selectinload(Match.job),
                    )
                )
            )
            .scalars()
            .all()
        )

        if not matches:
            return []

        all_policy_ids: set[UUID] = set()
        scored_matches: list[ScoredMatchData] = []
        match_counts: dict[UUID, int] = {}

        episode_ids: list[UUID] = []
        for match in matches:
            job = match.job
            if job is None:
                raise ValueError(f"Match {match.id} is missing job data.")
            episode_id = job.episode_id_uuid
            if episode_id is None:
                raise ValueError(f"Match {match.id} is missing a valid episode_id.")
            episode_ids.append(episode_id)
        agent_counts_by_episode: dict[UUID, dict[UUID, int]] = defaultdict(dict)
        if episode_ids:
            counts_result = await session.execute(
                select(Episode.id, EpisodePolicy.policy_version_id, EpisodePolicy.num_agents)
                .join(EpisodePolicy, EpisodePolicy.episode_id == Episode.id)
                .where(col(Episode.id).in_(episode_ids))
            )
            for row in counts_result.all():
                agent_counts_by_episode[row.id][row.policy_version_id] = row.num_agents

        for match in matches:
            if not match.players or any(mp.score is None for mp in match.players):
                continue

            job = match.job
            if job is None:
                raise ValueError(f"Match {match.id} is missing job data.")

            policy_scores: dict[UUID, float] = {}
            policy_version_ids: list[UUID] = []
            for mp in sorted(match.players, key=lambda x: x.policy_index):
                pv_id = mp.pool_player.policy_version_id
                policy_scores[pv_id] = mp.score  # type: ignore[assignment]
                if mp.policy_index >= len(policy_version_ids):
                    policy_version_ids.append(pv_id)
                all_policy_ids.add(pv_id)
                match_counts[pv_id] = match_counts.get(pv_id, 0) + 1

            episode_agent_counts = agent_counts_by_episode.get(job.episode_id_uuid)
            if not episode_agent_counts:
                continue

            scored_matches.append(
                ScoredMatchData(
                    match_id=match.id,
                    policy_scores=policy_scores,
                    assignments=match.assignments,
                    policy_version_ids=policy_version_ids,
                    policy_agent_counts=episode_agent_counts,
                )
            )

        if not scored_matches:
            return []

        scores = self.scorer.compute_scores(list(all_policy_ids), scored_matches)
        results = [(pv, score, match_counts.get(pv, 0)) for pv, score in scores.items()]
        return sorted(results, key=lambda x: x[1], reverse=True)
