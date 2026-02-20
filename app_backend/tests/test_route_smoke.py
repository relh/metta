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
from metta.app_backend.models.tournament import (
    Match,
    MatchPlayer,
    MatchStatus,
    Pool,
    PoolPlayer,
    Season,
    Team,
    TeamPolicyVersion,
)
from metta.app_backend.tournament.registry import SEASONS


@pytest_asyncio.fixture
async def seed_season(stats_repo: str) -> dict:  # type: ignore[unused-arg]
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


@pytest_asyncio.fixture
async def seed_teams_season(stats_repo: str) -> dict:  # type: ignore[unused-arg]
    async with db_session() as session:
        initial_fields = SEASONS["beta-teams-large"].get_initial_season_fields()
        season = Season(
            name="beta-teams-large",
            canonical=True,
            team_tournament_config=initial_fields["team_tournament_config"],
        )
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="stage-1")
        session.add(pool)
        await session.flush()

        policy = Policy(name=f"team-smoke-{uuid4().hex[:8]}", user_id="test-user")
        session.add(policy)
        await session.flush()

        pv = PolicyVersion(policy_id=policy.id, version=1)
        session.add(pv)
        await session.flush()

        pool_player = PoolPlayer(pool_id=pool.id, policy_version_id=pv.id)
        session.add(pool_player)
        await session.flush()

        team = Team(pool_id=pool.id)
        session.add(team)
        await session.flush()

        session.add(TeamPolicyVersion(team_id=team.id, policy_version_id=pv.id, position=0))
        await session.flush()

        return {
            "season_name": season.name,
            "policy_version_id": str(pv.id),
            "team_id": str(team.id),
        }


class TestTournamentRouteSmoke:
    def test_list_seasons(self, test_client: TestClient, softmax_headers: dict):
        r = test_client.get("/tournament/seasons", headers=softmax_headers)
        assert r.status_code == 200
        seasons = r.json()
        assert isinstance(seasons, list)
        if seasons:
            assert "display_name" not in seasons[0]
            assert isinstance(seasons[0]["summary"], str)
            assert "pools" in seasons[0]
            assert isinstance(seasons[0]["pools"], list)
            assert "entry_pool" in seasons[0]
            assert "leaderboard_pool" in seasons[0]
            assert "status" not in seasons[0]
            assert "entrant_count" not in seasons[0]

    @pytest.mark.asyncio
    async def test_get_season(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(
            f"/tournament/seasons/{seed_season['season_name']}?include_hidden=true", headers=softmax_headers
        )
        assert r.status_code == 200
        season = r.json()
        assert season["display_name"]
        assert isinstance(season["summary"], str)
        assert season["status"] in {"not_started", "in_progress", "complete"}
        assert season["started_at"] is None or isinstance(season["started_at"], str)
        assert isinstance(season["entrant_count"], int)
        assert isinstance(season["active_entrant_count"], int)
        assert isinstance(season["match_count"], int)
        assert isinstance(season["stage_count"], int)
        assert "pools" in season

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


class TestTeamRouteSmoke:
    @pytest.mark.asyncio
    async def test_get_teams(self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict):
        r = test_client.get(
            f"/tournament/seasons/{seed_teams_season['season_name']}/teams",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["cogs"][0]["policy"] is not None
        assert "matches" in data[0]

    @pytest.mark.asyncio
    async def test_get_teams_filter_by_policy(
        self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict
    ):
        r = test_client.get(
            f"/tournament/seasons/{seed_teams_season['season_name']}/teams"
            f"?policy_version_id={seed_teams_season['policy_version_id']}",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        assert len(r.json()) >= 1

    @pytest.mark.asyncio
    async def test_get_team_leaderboard_by_type(
        self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict
    ):
        r = test_client.get(
            f"/tournament/seasons/{seed_teams_season['season_name']}/leaderboard/team/stage-1",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_score_policies_leaderboard_by_type(
        self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict
    ):
        r = test_client.get(
            f"/tournament/seasons/{seed_teams_season['season_name']}/leaderboard/score-policies/policy-scores-1",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_score_policies_leaderboard(
        self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict
    ):
        r = test_client.get(
            f"/tournament/seasons/{seed_teams_season['season_name']}/score-policies-leaderboard",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    @pytest.mark.asyncio
    async def test_get_stages(self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict):
        r = test_client.get(
            f"/tournament/seasons/{seed_teams_season['season_name']}/stages",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_progress(self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict):
        r = test_client.get(
            f"/tournament/seasons/{seed_teams_season['season_name']}/progress",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "phase" in data

    @pytest.mark.asyncio
    async def test_start_season(self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict):
        r = test_client.post(
            f"/tournament/seasons/{seed_teams_season['season_name']}/start",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        assert r.json()["started"] is True
