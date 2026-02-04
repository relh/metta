from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlmodel import col, select

from metta.app_backend.database import db_session
from metta.app_backend.models.episodes import Episode, EpisodePolicy, EpisodePolicyMetric
from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, Pool, PoolPlayer, Season
from metta.app_backend.tournament.commissioners.base import CommissionerBase, MembershipChangeRequest
from metta.app_backend.tournament.referees.base import MatchCounts, MatchRequest, RefereeBase
from mettagrid.config.mettagrid_config import MettaGridConfig


class _TestCommissioner(CommissionerBase):
    season_name = "test-season"
    leaderboard_pool = "test-pool"
    referees: dict[str, object] = {"test-pool": object()}

    def get_new_submission_membership_changes(self, policy_version_id: UUID) -> list[MembershipChangeRequest]:
        return []

    async def get_membership_changes(self, pools: dict[str, Pool]) -> list[MembershipChangeRequest]:
        return []


class _TestReferee(RefereeBase):
    def make_env(self, seed: int) -> MettaGridConfig:
        raise NotImplementedError

    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
        limit: int = 0,
    ) -> list[MatchRequest]:
        return []


@pytest.mark.asyncio
async def test_sync_match_scores_uses_episode_policy_num_agents(isolated_stats_repo: str) -> None:
    commissioner = _TestCommissioner()

    episode_id = uuid4()

    async with db_session() as session:
        season = Season(name=commissioner.season_name, canonical=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name=commissioner.leaderboard_pool)
        session.add(pool)
        await session.flush()

        policy_a = Policy(name=f"policy-a-{uuid4()}", user_id="test-user")
        policy_b = Policy(name=f"policy-b-{uuid4()}", user_id="test-user")
        session.add(policy_a)
        session.add(policy_b)
        await session.flush()

        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        session.add(pv_a)
        session.add(pv_b)
        await session.flush()
        await session.refresh(pv_a, attribute_names=["internal_id"])
        await session.refresh(pv_b, attribute_names=["internal_id"])
        if pv_a.internal_id is None or pv_b.internal_id is None:
            raise RuntimeError("PolicyVersion internal_id not set after insert")

        pool_player_a = PoolPlayer(pool_id=pool.id, policy_version_id=pv_a.id)
        pool_player_b = PoolPlayer(pool_id=pool.id, policy_version_id=pv_b.id)
        session.add(pool_player_a)
        session.add(pool_player_b)
        await session.flush()

        job = JobRequest(
            job_type=JobType.episode,
            job={},
            user_id="test-user",
            status=JobStatus.completed,
            result={"episode_id": str(episode_id)},
        )
        session.add(job)
        await session.flush()

        # assignments say there is only 1 agent for policy A, but episode_policies
        # will record 2. The score should use the recorded episode count.
        match = Match(
            pool_id=pool.id,
            job_id=job.id,
            assignments=[0, 1],
            status=MatchStatus.completed,
        )
        session.add(match)
        await session.flush()

        session.add(MatchPlayer(match_id=match.id, pool_player_id=pool_player_a.id, policy_index=0))
        session.add(MatchPlayer(match_id=match.id, pool_player_id=pool_player_b.id, policy_index=1))

        episode = Episode(
            id=episode_id,
            data_uri="s3://test/episode.json",
            replay_url=None,
            thumbnail_url=None,
            attributes={},
            eval_task_id=None,
        )
        session.add(episode)
        await session.flush()
        await session.refresh(episode, attribute_names=["internal_id"])
        if episode.internal_id is None:
            raise RuntimeError("Episode internal_id not set after insert")

        session.add(EpisodePolicy(episode_id=episode.id, policy_version_id=pv_a.id, num_agents=2))
        session.add(EpisodePolicy(episode_id=episode.id, policy_version_id=pv_b.id, num_agents=1))

        session.add(
            EpisodePolicyMetric(
                episode_internal_id=episode.internal_id,
                pv_internal_id=pv_a.internal_id,
                metric_name="reward",
                value=10.0,
            )
        )
        session.add(
            EpisodePolicyMetric(
                episode_internal_id=episode.internal_id,
                pv_internal_id=pv_b.internal_id,
                metric_name="reward",
                value=3.0,
            )
        )

    async with db_session():
        updated = await commissioner._sync_match_scores()
        assert updated

    async with db_session() as session:
        rows = (
            await session.execute(
                select(PoolPlayer.policy_version_id, MatchPlayer.score)
                .join(MatchPlayer, col(MatchPlayer.pool_player_id) == col(PoolPlayer.id))
                .where(MatchPlayer.match_id == match.id)
            )
        ).all()
        scores_by_pv = {row.policy_version_id: row.score for row in rows}

        # Policy A: total reward 10.0, episode_policies says 2 agents => 5.0.
        assert scores_by_pv[pv_a.id] == pytest.approx(5.0)
        # Policy B: total reward 3.0, 1 agent => 3.0.
        assert scores_by_pv[pv_b.id] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_leaderboard_weighting_uses_episode_policy_num_agents(isolated_stats_repo: str) -> None:
    referee = _TestReferee()

    episode_id_1 = uuid4()
    episode_id_2 = uuid4()

    async with db_session() as session:
        season = Season(name="leaderboard-season", canonical=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="leaderboard-pool")
        session.add(pool)
        await session.flush()

        policy_a = Policy(name=f"policy-a-{uuid4()}", user_id="test-user")
        policy_b = Policy(name=f"policy-b-{uuid4()}", user_id="test-user")
        session.add(policy_a)
        session.add(policy_b)
        await session.flush()

        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        session.add(pv_a)
        session.add(pv_b)
        await session.flush()
        await session.refresh(pv_a, attribute_names=["internal_id"])
        await session.refresh(pv_b, attribute_names=["internal_id"])
        if pv_a.internal_id is None or pv_b.internal_id is None:
            raise RuntimeError("PolicyVersion internal_id not set after insert")

        pool_player_a = PoolPlayer(pool_id=pool.id, policy_version_id=pv_a.id)
        pool_player_b = PoolPlayer(pool_id=pool.id, policy_version_id=pv_b.id)
        session.add(pool_player_a)
        session.add(pool_player_b)
        await session.flush()

        job = JobRequest(
            job_type=JobType.episode,
            job={},
            user_id="test-user",
            status=JobStatus.completed,
            result={"episode_id": str(episode_id_1)},
        )
        session.add(job)
        await session.flush()

        # assignments say there is only 1 agent for policy A, but episode_policies
        # will record 2. Leaderboard weighting should use the recorded counts.
        match = Match(
            pool_id=pool.id,
            job_id=job.id,
            assignments=[0, 1],
            status=MatchStatus.completed,
        )
        session.add(match)
        await session.flush()

        # Per-agent scores are based on episode_policies counts:
        # Policy A total 9.0 over 2 agents => 4.5.
        session.add(MatchPlayer(match_id=match.id, pool_player_id=pool_player_a.id, policy_index=0, score=4.5))
        session.add(MatchPlayer(match_id=match.id, pool_player_id=pool_player_b.id, policy_index=1, score=3.0))

        episode = Episode(
            id=episode_id_1,
            data_uri="s3://test/episode.json",
            replay_url=None,
            thumbnail_url=None,
            attributes={},
            eval_task_id=None,
        )
        session.add(episode)
        await session.flush()
        await session.refresh(episode, attribute_names=["internal_id"])
        if episode.internal_id is None:
            raise RuntimeError("Episode internal_id not set after insert")

        session.add(EpisodePolicy(episode_id=episode.id, policy_version_id=pv_a.id, num_agents=2))
        session.add(EpisodePolicy(episode_id=episode.id, policy_version_id=pv_b.id, num_agents=1))

        session.add(
            EpisodePolicyMetric(
                episode_internal_id=episode.internal_id,
                pv_internal_id=pv_a.internal_id,
                metric_name="reward",
                value=9.0,
            )
        )
        session.add(
            EpisodePolicyMetric(
                episode_internal_id=episode.internal_id,
                pv_internal_id=pv_b.internal_id,
                metric_name="reward",
                value=3.0,
            )
        )

        job_2 = JobRequest(
            job_type=JobType.episode,
            job={},
            user_id="test-user",
            status=JobStatus.completed,
            result={"episode_id": str(episode_id_2)},
        )
        session.add(job_2)
        await session.flush()

        match_2 = Match(
            pool_id=pool.id,
            job_id=job_2.id,
            assignments=[0, 1, 1],
            status=MatchStatus.completed,
        )
        session.add(match_2)
        await session.flush()

        # Second match has consistent counts and a low score for policy A so
        # the agent-share weighting affects the overall average.
        session.add(MatchPlayer(match_id=match_2.id, pool_player_id=pool_player_a.id, policy_index=0, score=0.0))
        session.add(MatchPlayer(match_id=match_2.id, pool_player_id=pool_player_b.id, policy_index=1, score=0.0))

        episode_2 = Episode(
            id=episode_id_2,
            data_uri="s3://test/episode-2.json",
            replay_url=None,
            thumbnail_url=None,
            attributes={},
            eval_task_id=None,
        )
        session.add(episode_2)
        await session.flush()
        await session.refresh(episode_2, attribute_names=["internal_id"])
        if episode_2.internal_id is None:
            raise RuntimeError("Episode internal_id not set after insert")

        session.add(EpisodePolicy(episode_id=episode_2.id, policy_version_id=pv_a.id, num_agents=1))
        session.add(EpisodePolicy(episode_id=episode_2.id, policy_version_id=pv_b.id, num_agents=2))

        session.add(
            EpisodePolicyMetric(
                episode_internal_id=episode_2.internal_id,
                pv_internal_id=pv_a.internal_id,
                metric_name="reward",
                value=0.0,
            )
        )
        session.add(
            EpisodePolicyMetric(
                episode_internal_id=episode_2.internal_id,
                pv_internal_id=pv_b.internal_id,
                metric_name="reward",
                value=0.0,
            )
        )

    async with db_session():
        leaderboard = await referee.get_leaderboard(pool.id)

    scores_by_pv = {pv_id: score for pv_id, score, _ in leaderboard}
    # Policy A weighted score:
    # (4.5 * 2/3 + 0.0 * 1/3) / (2/3 + 1/3) => 3.0.
    assert scores_by_pv[pv_a.id] == pytest.approx(3.0)
