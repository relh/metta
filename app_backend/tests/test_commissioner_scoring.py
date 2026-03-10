from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Sequence, cast
from uuid import UUID, uuid4

import pytest
from sqlmodel import col, select

import metta.app_backend.database as database
from metta.app_backend.database import db_session
from metta.app_backend.models.episodes import Episode, EpisodePolicy, EpisodePolicyMetric
from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, Pool, PoolPlayer, Season
from metta.app_backend.tournament.commissioners.base import CommissionerBase, MembershipChangeRequest
from metta.app_backend.tournament.commissioners.teams.config import GameEnvGenerator, PolicyEvalStage
from metta.app_backend.tournament.referees.base import MatchCounts, MatchRequest, RefereeBase, ScoredMatchData
from metta.app_backend.tournament.referees.leaderboard_rows import group_match_rows
from metta.app_backend.tournament.referees.teams.policy_stage import MockPolicyStageReferee
from mettagrid.config.mettagrid_config import MettaGridConfig


class _TestCommissioner(CommissionerBase):
    season_name = "test-season"
    display_name = "Test Season"
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


class _ExecuteRowsResult:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class _RecordingLeaderboardSession:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows
        self.execute_count = 0
        self.queries: list[str] = []

    async def execute(self, query: object) -> _ExecuteRowsResult:
        self.execute_count += 1
        self.queries.append(str(query))
        return _ExecuteRowsResult(self._rows)


class _RecordingScorer:
    def __init__(self) -> None:
        self.scored_matches: list[ScoredMatchData] = []

    def compute_scores(
        self,
        policy_version_ids: Sequence[UUID],
        matches: Sequence[Any],
    ) -> dict[UUID, float]:
        self.scored_matches = [cast(ScoredMatchData, match) for match in matches]
        if not self.scored_matches:
            return {}
        first_match = self.scored_matches[0]
        return {policy_id: first_match.policy_scores[policy_id] for policy_id in policy_version_ids}


def test_group_match_rows_collects_joined_agent_counts() -> None:
    match_id = uuid4()
    policy_a = uuid4()
    policy_b = uuid4()
    rows = [
        SimpleNamespace(
            match_id=match_id,
            assignments=[0, 1, 1],
            policy_index=0,
            score=1.0,
            policy_version_id=policy_a,
            num_agents=1,
        ),
        SimpleNamespace(
            match_id=match_id,
            assignments=[0, 1, 1],
            policy_index=1,
            score=2.0,
            policy_version_id=policy_b,
            num_agents=2,
        ),
    ]

    grouped = group_match_rows(rows, include_num_agents=True)

    assert grouped[match_id].players == [(0, 1.0, policy_a), (1, 2.0, policy_b)]
    assert grouped[match_id].policy_agent_counts == {policy_a: 1, policy_b: 2}


@pytest.mark.asyncio
async def test_get_leaderboard_with_stats_joins_episode_policy_agent_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    match_id = uuid4()
    policy_a = uuid4()
    policy_b = uuid4()
    session = _RecordingLeaderboardSession(
        [
            SimpleNamespace(
                match_id=match_id,
                assignments=[0, 1, 1],
                policy_index=0,
                score=1.0,
                policy_version_id=policy_a,
                num_agents=1,
            ),
            SimpleNamespace(
                match_id=match_id,
                assignments=[0, 1, 1],
                policy_index=1,
                score=2.0,
                policy_version_id=policy_b,
                num_agents=2,
            ),
        ]
    )
    scorer = _RecordingScorer()
    referee = _TestReferee()
    referee.scorer = cast(Any, scorer)
    monkeypatch.setattr(database, "get_db", lambda: session)

    leaderboard = await referee.get_leaderboard_with_stats(uuid4())

    assert session.execute_count == 1
    assert "LEFT OUTER JOIN episode_policies" in session.queries[0]
    assert " IN (" not in session.queries[0].upper()
    assert len(scorer.scored_matches) == 1
    assert scorer.scored_matches[0].policy_agent_counts == {policy_a: 1, policy_b: 2}
    assert {row.policy_version_id for row in leaderboard} == {policy_a, policy_b}


@pytest.mark.asyncio
async def test_sync_match_scores_uses_episode_policy_num_agents(stats_repo: str) -> None:
    commissioner = _TestCommissioner(season_id=uuid4())

    episode_id = uuid4()

    async with db_session() as session:
        season = Season(name=commissioner.season_name, canonical=True)
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

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
async def test_leaderboard_weighting_uses_episode_policy_num_agents(stats_repo: str) -> None:
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
        leaderboard_with_stats = await referee.get_leaderboard_with_stats(pool.id)

    scores_by_pv = {pv_id: score for pv_id, score, _ in leaderboard}
    stddev_by_pv = {row.policy_version_id: row.score_stddev for row in leaderboard_with_stats}
    # Policy A weighted score:
    # (4.5 * 2/3 + 0.0 * 1/3) / (2/3 + 1/3) => 3.0.
    assert scores_by_pv[pv_a.id] == pytest.approx(3.0)
    # Weighted stddev for A around mean=3.0:
    # sqrt((2/3*(4.5-3)^2 + 1/3*(0-3)^2) / (2/3+1/3)) => sqrt(4.5) ≈ 2.1213
    assert stddev_by_pv[pv_a.id] == pytest.approx(2.1213203435596424)


@pytest.mark.asyncio
async def test_leaderboard_uses_assignments_when_episode_counts_missing(stats_repo: str) -> None:
    referee = MockPolicyStageReferee(
        stage=PolicyEvalStage(policies_per_team=1, matches_per_combo=1),
        game=GameEnvGenerator(num_agents=8),
    )
    pool_id: UUID
    pv_a_id: UUID
    pv_b_id: UUID

    async with db_session() as session:
        season = Season(name=f"leaderboard-no-episode-{uuid4()}", canonical=True)
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
        pv_a_id = pv_a.id
        pv_b_id = pv_b.id

        pool_player_a = PoolPlayer(pool_id=pool.id, policy_version_id=pv_a.id)
        pool_player_b = PoolPlayer(pool_id=pool.id, policy_version_id=pv_b.id)
        session.add(pool_player_a)
        session.add(pool_player_b)
        await session.flush()

        # No job_id / episode_id here: this matches mock tournament matches.
        match_1 = Match(
            pool_id=pool.id,
            assignments=[0, 0, 0, 1],
            status=MatchStatus.completed,
        )
        session.add(match_1)
        await session.flush()
        session.add(MatchPlayer(match_id=match_1.id, pool_player_id=pool_player_a.id, policy_index=0, score=1.0))
        session.add(MatchPlayer(match_id=match_1.id, pool_player_id=pool_player_b.id, policy_index=1, score=0.0))

        match_2 = Match(
            pool_id=pool.id,
            assignments=[0, 1, 1, 1],
            status=MatchStatus.completed,
        )
        session.add(match_2)
        await session.flush()
        session.add(MatchPlayer(match_id=match_2.id, pool_player_id=pool_player_a.id, policy_index=0, score=0.0))
        session.add(MatchPlayer(match_id=match_2.id, pool_player_id=pool_player_b.id, policy_index=1, score=0.5))
        pool_id = pool.id

    async with db_session():
        leaderboard = await referee.get_leaderboard(pool_id)

    scores_by_pv = {pv_id: score for pv_id, score, _ in leaderboard}
    matches_by_pv = {pv_id: match_count for pv_id, _, match_count in leaderboard}

    # Policy A: 1.0 * (3/4) + 0.0 * (1/4) = 0.75
    assert scores_by_pv[pv_a_id] == pytest.approx(0.75)
    # Policy B: 0.0 * (1/4) + 0.5 * (3/4) = 0.375
    assert scores_by_pv[pv_b_id] == pytest.approx(0.375)
    assert matches_by_pv[pv_a_id] == 2
    assert matches_by_pv[pv_b_id] == 2
