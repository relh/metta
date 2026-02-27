"""Smoke tests for public API endpoints.

Validates that query construction and relationship loading don't crash.
These catch SQLAlchemy loader chain errors (e.g. raiseload("*") misuse)
that only surface at request time.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from metta.app_backend.auth import User
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
from metta.app_backend.test_support.client_adapter import get_user_headers
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
async def seed_public_season(stats_repo: str) -> dict:  # type: ignore[unused-arg]
    async with db_session() as session:
        season = Season(name="beta-cvc", canonical=True, public=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="test-pool")
        session.add(pool)
        await session.flush()

        policy = Policy(name=f"public-smoke-policy-{uuid4().hex[:8]}", user_id="test-user")
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
        await session.flush()

        return {
            "season_name": season.name,
            "match_id": str(match.id),
            "policy_version_id": str(pv.id),
        }


@pytest_asyncio.fixture
async def seed_or_logic_season(stats_repo: str) -> dict:  # type: ignore[unused-arg]
    """Fixture for testing OR logic in policy_version_ids filter.

    Creates a season with two separate policies, each having its own match.
    Used to verify that filtering by multiple policy_version_ids returns
    matches containing ANY of them (OR logic), not ALL of them (AND logic).
    """
    async with db_session() as session:
        # Use "test-season" because it's a registered season name (in beta_test.py commissioner)
        season = Season(name="test-season", canonical=True)
        session.add(season)
        await session.flush()

        pool = Pool(season_id=season.id, name="test-pool")
        session.add(pool)
        await session.flush()

        # Create two separate policies
        policy_a = Policy(name=f"policy-a-{uuid4().hex[:8]}", user_id="test-user")
        policy_b = Policy(name=f"policy-b-{uuid4().hex[:8]}", user_id="test-user")
        session.add(policy_a)
        session.add(policy_b)
        await session.flush()

        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        session.add(pv_a)
        session.add(pv_b)
        await session.flush()

        pp_a = PoolPlayer(pool_id=pool.id, policy_version_id=pv_a.id)
        pp_b = PoolPlayer(pool_id=pool.id, policy_version_id=pv_b.id)
        session.add(pp_a)
        session.add(pp_b)
        await session.flush()

        # Create match containing ONLY policy A
        match_a = Match(pool_id=pool.id, assignments=[0], status=MatchStatus.completed)
        session.add(match_a)
        await session.flush()
        session.add(MatchPlayer(match_id=match_a.id, pool_player_id=pp_a.id, policy_index=0, score=1.0))

        # Create match containing ONLY policy B
        match_b = Match(pool_id=pool.id, assignments=[0], status=MatchStatus.completed)
        session.add(match_b)
        await session.flush()
        session.add(MatchPlayer(match_id=match_b.id, pool_player_id=pp_b.id, policy_index=0, score=2.0))
        await session.flush()

        return {
            "season_name": season.name,
            "pv_a_id": str(pv_a.id),
            "pv_b_id": str(pv_b.id),
            "match_a_id": str(match_a.id),
            "match_b_id": str(match_b.id),
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
            "season_id": str(season.id),
            "policy_version_id": str(pv.id),
            "team_id": str(team.id),
        }


@pytest_asyncio.fixture
async def seed_rollable_freeplay_season(stats_repo: str) -> dict:  # type: ignore[unused-arg]
    async with db_session() as session:
        season_name = "test-season"
        commissioner_cls = SEASONS[season_name]
        season = Season(name=season_name, canonical=True)
        session.add(season)
        await session.flush()

        entry_pool = Pool(season_id=season.id, name=commissioner_cls.entry_pool)
        session.add(entry_pool)
        await session.flush()

        policy = Policy(name=f"rollable-{uuid4().hex[:8]}", user_id="test-user")
        session.add(policy)
        await session.flush()

        policy_version = PolicyVersion(policy_id=policy.id, version=1)
        session.add(policy_version)
        await session.flush()

        session.add(PoolPlayer(pool_id=entry_pool.id, policy_version_id=policy_version.id, retired=False))
        await session.flush()

        return {
            "season_name": season.name,
            "season_id": str(season.id),
            "policy_version_id": str(policy_version.id),
        }


class TestTournamentRouteSmoke:
    def test_list_seasons(self, test_client: TestClient, softmax_headers: dict):
        r = test_client.get("/tournament/seasons", headers=softmax_headers)
        assert r.status_code == 200
        seasons = r.json()
        assert isinstance(seasons, list)
        if seasons:
            assert seasons[0]["display_name"]
            assert isinstance(seasons[0]["summary"], str)
            assert "pools" in seasons[0]
            assert isinstance(seasons[0]["pools"], list)
            assert "entry_pool" in seasons[0]
            assert "leaderboard_pool" in seasons[0]
            assert seasons[0]["tournament_type"] in {"freeplay", "team"}
            assert "status" not in seasons[0]
            assert "entrant_count" not in seasons[0]

    @pytest.mark.asyncio
    async def test_list_available_compat_versions(self, test_client: TestClient):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.6", "0.5"]),
        ):
            response = test_client.get("/tournament/compat-versions")

        assert response.status_code == 200
        assert response.json() == ["0.6", "0.5"]

    @pytest.mark.asyncio
    async def test_get_season(self, test_client: TestClient, softmax_headers: dict, seed_season: dict):
        r = test_client.get(f"/tournament/seasons/{seed_season['season_name']}", headers=softmax_headers)
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
        r = test_client.get(f"/tournament/seasons/{seed_season['season_name']}/matches", headers=softmax_headers)
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
            f"/tournament/seasons/{seed_season['season_name']}/leaderboard",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "score_stddev" in data[0]

    @pytest.mark.asyncio
    async def test_get_matches_policy_version_ids_uses_or_logic(
        self, test_client: TestClient, softmax_headers: dict, seed_or_logic_season: dict
    ):
        """Verify that filtering by multiple policy_version_ids uses OR logic.

        When a user has multiple policy versions (e.g. v1, v2, v3), the matches
        endpoint should return matches containing ANY of those versions, not
        matches containing ALL of them (which would typically be zero).
        """
        # Query for matches containing EITHER policy A OR policy B
        # With OR logic: should return 2 matches
        # With AND logic (bug): would return 0 matches
        r = test_client.get(
            f"/tournament/seasons/{seed_or_logic_season['season_name']}/matches"
            f"?policy_version_ids={seed_or_logic_season['pv_a_id']}"
            f"&policy_version_ids={seed_or_logic_season['pv_b_id']}",
            headers=softmax_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2, "policy_version_ids filter should use OR logic, returning matches with ANY policy"

        # Verify we got both matches
        match_ids = {m["id"] for m in data}
        assert seed_or_logic_season["match_a_id"] in match_ids
        assert seed_or_logic_season["match_b_id"] in match_ids

    @pytest.mark.asyncio
    async def test_roll_freeplay_season(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.6"]),
        ):
            response = test_client.post(
                f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/roll",
                json={"compat_version": "0.6"},
                headers=softmax_headers,
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == seed_rollable_freeplay_season["season_name"]
        assert payload["version"] == 2
        assert payload["canonical"] is True
        assert payload["tournament_type"] == "freeplay"
        assert payload["compat_version"] == "0.6"

        versions_response = test_client.get(
            f"/tournament/seasons/{seed_rollable_freeplay_season['season_name']}/versions",
            headers=softmax_headers,
        )
        assert versions_response.status_code == 200
        versions = versions_response.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 2
        assert versions[0]["canonical"] is True
        assert versions[1]["version"] == 1
        assert versions[1]["canonical"] is False

    @pytest.mark.asyncio
    async def test_roll_team_season(self, test_client: TestClient, softmax_headers: dict, seed_teams_season: dict):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.6"]),
        ):
            response = test_client.post(
                f"/tournament/seasons/{seed_teams_season['season_id']}/roll",
                json={"compat_version": "0.6"},
                headers=softmax_headers,
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == seed_teams_season["season_name"]
        assert payload["version"] == 2
        assert payload["canonical"] is True
        assert payload["tournament_type"] == "team"
        assert payload["compat_version"] == "0.6"

    @pytest.mark.asyncio
    async def test_roll_freeplay_requires_compat_version(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        response = test_client.post(
            f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/roll",
            json={"compat_version": "   "},
            headers=softmax_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "compat_version is required"

    @pytest.mark.asyncio
    async def test_roll_freeplay_requires_authentication(
        self, test_client: TestClient, seed_rollable_freeplay_season: dict
    ):
        response = test_client.post(
            f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/roll",
            json={"compat_version": "0.6"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Failed to authenticate"

    @pytest.mark.asyncio
    async def test_roll_freeplay_requires_softmax_membership(
        self, test_client: TestClient, regular_headers: dict, seed_rollable_freeplay_season: dict
    ):
        response = test_client.post(
            f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/roll",
            json={"compat_version": "0.6"},
            headers=regular_headers,
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "User is not a softmax team member"

    @pytest.mark.asyncio
    async def test_roll_freeplay_by_season_id(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.6"]),
        ):
            response = test_client.post(
                f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/roll",
                json={"compat_version": "0.6"},
                headers=softmax_headers,
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == seed_rollable_freeplay_season["season_name"]
        assert payload["version"] == 2

    @pytest.mark.asyncio
    async def test_roll_freeplay_with_migrate_active_players(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.6"]),
        ):
            response = test_client.post(
                f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/roll",
                json={"compat_version": "0.6", "migrate_active_players": True},
                headers=softmax_headers,
            )
        assert response.status_code == 200
        season_name = seed_rollable_freeplay_season["season_name"]
        detail = test_client.get(f"/tournament/seasons/{season_name}", headers=softmax_headers)
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["version"] == 2
        assert payload["entrant_count"] == 1
        assert payload["active_entrant_count"] == 1

    @pytest.mark.asyncio
    async def test_roll_freeplay_rejects_unavailable_compat_version(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.5"]),
        ):
            response = test_client.post(
                f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/roll",
                json={"compat_version": "0.6"},
                headers=softmax_headers,
            )
        assert response.status_code == 400
        assert response.json()["detail"].startswith("compat_version 0.6 is not available in")

    @pytest.mark.asyncio
    async def test_update_current_season_compat_version(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.7", "0.6"]),
        ):
            response = test_client.post(
                f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}"
                "/update-current-season-compat-version",
                json={"compat_version": "0.7"},
                headers=softmax_headers,
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == seed_rollable_freeplay_season["season_name"]
        assert payload["version"] == 1
        assert payload["canonical"] is True
        assert payload["compat_version"] == "0.7"

    @pytest.mark.asyncio
    async def test_update_current_season_compat_version_requires_value(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        response = test_client.post(
            f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}/update-current-season-compat-version",
            json={"compat_version": "   "},
            headers=softmax_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "compat_version is required"

    @pytest.mark.asyncio
    async def test_update_current_season_compat_version_rejects_unavailable(
        self, test_client: TestClient, softmax_headers: dict, seed_rollable_freeplay_season: dict
    ):
        with patch(
            "metta.app_backend.routes.tournament_routes._list_available_episode_runner_compat_versions",
            new=AsyncMock(return_value=["0.6"]),
        ):
            response = test_client.post(
                f"/tournament/seasons/{seed_rollable_freeplay_season['season_id']}"
                "/update-current-season-compat-version",
                json={"compat_version": "0.7"},
                headers=softmax_headers,
            )
        assert response.status_code == 400
        assert response.json()["detail"].startswith("compat_version 0.7 is not available in")

    @pytest.mark.asyncio
    async def test_list_match_policy_logs_owner(self, test_client: TestClient, seed_public_season: dict):
        """Policy owner can list their policy logs in a match."""
        owner_headers = get_user_headers(User(id="test-user", email="test@example.com", is_softmax_team_member=False))
        files = ["policy_agent_0.txt"]
        with patch("boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.list_objects_v2.return_value = {"Contents": [{"Key": f"jobs/xxx/{f}"} for f in files]}
            mock_boto.return_value = mock_s3

            r = test_client.get(
                f"/tournament/matches/{seed_public_season['match_id']}/{seed_public_season['policy_version_id']}/policy-logs",
                headers=owner_headers,
            )

        assert r.status_code == 200
        assert r.json() == files

    @pytest.mark.asyncio
    async def test_get_match_policy_log_owner(self, test_client: TestClient, seed_public_season: dict):
        """Policy owner can get a specific agent's policy log."""
        owner_headers = get_user_headers(User(id="test-user", email="test@example.com", is_softmax_team_member=False))
        with patch("boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"test log content")}
            mock_boto.return_value = mock_s3

            r = test_client.get(
                f"/tournament/matches/{seed_public_season['match_id']}/{seed_public_season['policy_version_id']}/policy-logs/0",
                headers=owner_headers,
            )

        assert r.status_code == 200
        assert r.text == "test log content"

    @pytest.mark.asyncio
    async def test_match_policy_logs_forbidden_for_non_owner(
        self, test_client: TestClient, regular_headers: dict, seed_public_season: dict
    ):
        """Non-owner gets 403 when accessing another user's policy logs."""
        r = test_client.get(
            f"/tournament/matches/{seed_public_season['match_id']}/{seed_public_season['policy_version_id']}/policy-logs",
            headers=regular_headers,
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_match_policy_logs_forbidden_for_softmax_non_owner(
        self, test_client: TestClient, softmax_headers: dict, seed_public_season: dict
    ):
        """Softmax team members get 403 when accessing another user's policy logs."""
        r = test_client.get(
            f"/tournament/matches/{seed_public_season['match_id']}/{seed_public_season['policy_version_id']}/policy-logs",
            headers=softmax_headers,
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_get_match_policy_log_wrong_agent_forbidden(self, test_client: TestClient, seed_public_season: dict):
        """Requesting a log for an agent that doesn't run the specified policy returns 403."""
        owner_headers = get_user_headers(User(id="test-user", email="test@example.com", is_softmax_team_member=False))
        r = test_client.get(
            f"/tournament/matches/{seed_public_season['match_id']}/{seed_public_season['policy_version_id']}/policy-logs/99",
            headers=owner_headers,
        )
        assert r.status_code == 403


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
        if data:
            assert "team_ranks" in data[0]
            assert isinstance(data[0]["team_ranks"], list)

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
