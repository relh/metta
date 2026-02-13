"""Smoke tests for public API endpoints.

Validates that query construction and relationship loading don't crash.
These catch SQLAlchemy loader chain errors (e.g. raiseload("*") misuse)
that only surface at request time.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from metta.app_backend.database import db_session
from metta.app_backend.models.episodes import Episode, EpisodeJob, EpisodeTag
from metta.app_backend.models.job_request import JobPolicyVersion, JobRequest, JobStatus, JobType
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, Pool, PoolPlayer, Season


@pytest_asyncio.fixture
async def seed_season(stats_repo: str) -> dict:
    _ = stats_repo
    async with db_session() as session:
        season = Season(name="test-season", canonical=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="test-pool")
        session.add(pool)
        await session.flush()

        policy = Policy(name=f"smoke-policy-{uuid4().hex[:8]}", user_id="test-user")
        session.add(policy)
        await session.flush()

        pv = PolicyVersion(policy_id=policy.id, version=1)
        session.add(pv)
        await session.flush()

        pool_player = PoolPlayer(pool_id=pool.id, policy_version_id=pv.id)
        session.add(pool_player)
        await session.flush()

        job = JobRequest(
            job_type=JobType.episode,
            job={"assignments": [0]},
            user_id="test-user",
            status=JobStatus.completed,
            result={"episode_id": str(uuid4())},
        )
        session.add(job)
        await session.flush()

        jpv = JobPolicyVersion(job_id=job.id, position=0, policy_version_id=pv.id)
        session.add(jpv)
        await session.flush()

        match = Match(pool_id=pool.id, job_id=job.id, assignments=[0], status=MatchStatus.completed)
        session.add(match)
        await session.flush()

        session.add(MatchPlayer(match_id=match.id, pool_player_id=pool_player.id, policy_index=0, score=1.0))

        episode = Episode(data_uri="s3://test/ep.json")
        session.add(episode)
        await session.flush()

        session.add(EpisodeTag(episode_id=episode.id, key="map", value="arena"))
        session.add(EpisodeJob(episode_id=episode.id, job_id=job.id))
        await session.flush()

        return {
            "season_name": season.name,
            "match_id": str(match.id),
            "episode_id": str(episode.id),
            "policy_version_id": str(pv.id),
        }


class TestTournamentRouteSmoke:
    def test_list_seasons(self, test_client: TestClient, softmax_headers: dict):
        r = test_client.get("/tournament/seasons", headers=softmax_headers)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_get_season(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(
            f"/tournament/seasons/{seed_season['season_name']}?include_hidden=true", headers=softmax_headers
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_get_matches(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(
            f"/tournament/seasons/{seed_season['season_name']}/matches?include_hidden=true", headers=softmax_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_match(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(f"/tournament/matches/{seed_season['match_id']}", headers=softmax_headers)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_get_leaderboard(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(
            f"/tournament/seasons/{seed_season['season_name']}/leaderboard?include_hidden=true",
            headers=softmax_headers,
        )
        assert r.status_code == 200


class TestEpisodeRouteSmoke:
    @pytest.mark.asyncio
    async def test_get_episode(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(f"/episodes/{seed_season['episode_id']}", headers=softmax_headers)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_list_episodes(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get("/episodes", headers=softmax_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    @pytest.mark.asyncio
    async def test_list_episodes_by_policy(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(f"/episodes?policy_version_id={seed_season['policy_version_id']}", headers=softmax_headers)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_list_episodes_by_tag(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get("/episodes?tags=map:arena", headers=softmax_headers)
        assert r.status_code == 200
