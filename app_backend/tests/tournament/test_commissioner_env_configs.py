from __future__ import annotations

import hashlib
import json
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlmodel import select

from metta.app_backend.database import db_session
from metta.app_backend.models.tournament import MettagridEnvConfig, Pool, PoolPlayer, Season
from metta.app_backend.tournament.commissioners.base import CommissionerBase, MembershipChangeRequest
from metta.app_backend.tournament.referees.base import MatchCounts, MatchRequest, RefereeBase
from metta.app_backend.tournament.referees.envs import make_cogsguard_env
from mettagrid.config.mettagrid_config import MettaGridConfig


class _StubCommissioner(CommissionerBase):
    season_name = "test-season"
    display_name = "Test Season"
    leaderboard_pool = None  # type: ignore[assignment]
    entry_pool = None  # type: ignore[assignment]
    referees: dict[str, RefereeBase] = {}

    def get_new_submission_membership_changes(self, policy_version_id: UUID) -> list[MembershipChangeRequest]:
        return []

    async def get_membership_changes(self, pools: dict[str, Pool]) -> list[MembershipChangeRequest]:
        return []


class _StubReferee(RefereeBase):
    env_name = "test-env"
    num_agents: int = 4

    def make_env(self, seed: int) -> MettaGridConfig:
        return make_cogsguard_env(seed=seed, num_agents=self.num_agents)

    def get_matches_to_schedule(
        self,
        _players: list[PoolPlayer],
        _match_counts: MatchCounts,
        _limit: int = 0,
    ) -> list[MatchRequest]:
        return []


class _AltNameSameConfigReferee(_StubReferee):
    env_name = "test-env-alt"


def test_env_config_generate_with_map_seed_sets_seed_without_mutating_input() -> None:
    env_config = make_cogsguard_env(seed=11, num_agents=4).model_dump(mode="json")
    env_row = MettagridEnvConfig(config_hash="abc123", config=env_config)
    seeded = env_row.generate_with_map_seed(map_seed=97)
    assert seeded.model_dump(mode="json")["game"]["map_builder"]["seed"] == 97
    assert env_row.config["game"]["map_builder"]["seed"] == 11


def test_env_config_generate_with_map_seed_requires_existing_seed_field() -> None:
    env_config = make_cogsguard_env(seed=11, num_agents=4).model_dump(mode="json")
    del env_config["game"]["map_builder"]["seed"]
    env_row = MettagridEnvConfig(config_hash="abc123", config=env_config)
    with pytest.raises(KeyError, match="env_config\\.game\\.map_builder\\.seed"):
        env_row.generate_with_map_seed(map_seed=97)


@pytest.mark.asyncio
async def test_create_env_config_persists_metadata(
    stats_repo: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = stats_repo
    referee = _StubReferee()
    commissioner = _StubCommissioner(season_id=uuid4())
    compat_version = "0.5"
    git_commit = "deadbeef"
    monkeypatch.setattr("metta.app_backend.tournament.commissioners.base.settings.GIT_COMMIT", git_commit)

    created_id: UUID

    async with db_session():
        with patch(
            "metta.app_backend.tournament.commissioners.base.get_compat_version",
            return_value=compat_version,
        ):
            created = await commissioner._get_or_create_env_config(referee, compat_version=compat_version)
            created_id = created.id

    async with db_session() as session:
        row = (
            await session.execute(select(MettagridEnvConfig).where(MettagridEnvConfig.id == created_id))
        ).scalar_one()
        assert row.name == referee.env_name
        assert row.compat_version == compat_version
        assert row.git_commit == git_commit
        assert row.num_agents == referee.num_agents


@pytest.mark.asyncio
async def test_get_or_create_env_config_allows_same_hash_across_env_names(stats_repo: str) -> None:
    _ = stats_repo
    commissioner = _StubCommissioner(season_id=uuid4())
    referee_a = _StubReferee()
    referee_b = _AltNameSameConfigReferee()

    async with db_session():
        first = await commissioner._get_or_create_env_config(referee_a, compat_version=None)
        second = await commissioner._get_or_create_env_config(referee_b, compat_version=None)

        assert first.id != second.id
        assert first.config_hash == second.config_hash
        assert first.name == referee_a.env_name
        assert second.name == referee_b.env_name


@pytest.mark.asyncio
async def test_ensure_pools_exist_rejects_compat_regeneration_on_server_mismatch(stats_repo: str) -> None:
    _ = stats_repo
    referee = _StubReferee()
    commissioner = _StubCommissioner(season_id=uuid4())
    season_id: UUID

    async with db_session() as session:
        season = Season(name=f"compat-mismatch-{uuid4().hex[:8]}", canonical=True, compat_version="0.5")
        session.add(season)
        await session.flush()
        season_id = season.id

        env = referee.make_env(seed=0).model_dump(mode="json")
        env_hash = hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest()
        env_row = MettagridEnvConfig(
            config_hash=env_hash,
            config=env,
            name=referee.env_name,
            compat_version="0.4",
        )
        session.add(env_row)
        await session.flush()
        session.add(
            Pool(
                season_id=season.id,
                name="pool-1",
                env_config_id=env_row.id,
            )
        )
        await session.commit()

    async with db_session() as session:
        season = (await session.execute(select(Season).where(Season.id == season_id))).scalar_one()
        with pytest.raises(RuntimeError, match="cannot generate"):
            await commissioner._ensure_pools_exist(season, {"pool-1": referee})


@pytest.mark.asyncio
async def test_ensure_pools_exist_regenerates_pool_env_config_when_compat_changes(
    stats_repo: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = stats_repo
    referee = _StubReferee()
    commissioner = _StubCommissioner(season_id=uuid4())
    season_id: UUID
    pool_id: UUID

    async with db_session() as session:
        season = Season(name=f"compat-regenerate-{uuid4().hex[:8]}", canonical=True, compat_version="0.5")
        session.add(season)
        await session.flush()
        season_id = season.id

        legacy_env = referee.make_env(seed=7).model_dump(mode="json")
        legacy_hash = hashlib.sha256(json.dumps(legacy_env, sort_keys=True).encode()).hexdigest()
        env_row = MettagridEnvConfig(
            config_hash=legacy_hash,
            config=legacy_env,
            name=None,
            compat_version="0.4",
        )
        session.add(env_row)
        await session.flush()
        legacy_env_id = env_row.id

        pool = Pool(season_id=season.id, name="pool-1", env_config_id=env_row.id)
        session.add(pool)
        await session.flush()
        pool_id = pool.id
        await session.commit()

    monkeypatch.setattr("metta.app_backend.tournament.commissioners.base.settings.GIT_COMMIT", "new-compat-commit")
    async with db_session() as session:
        season = (await session.execute(select(Season).where(Season.id == season_id))).scalar_one()
        with patch(
            "metta.app_backend.tournament.commissioners.base.get_compat_version",
            return_value="0.5",
        ):
            pools = await commissioner._ensure_pools_exist(season, {"pool-1": referee})

        pool = pools["pool-1"]
        assert pool.id == pool_id
        assert pool.env_config is not None
        assert pool.env_config.id != legacy_env_id
        assert pool.env_config.compat_version == "0.5"
        assert pool.env_config.name == referee.env_name
        assert pool.env_config.git_commit == "new-compat-commit"
        assert pool.env_config.config == referee.make_env(seed=0).model_dump(mode="json")


@pytest.mark.asyncio
async def test_ensure_pools_exist_allows_existing_env_without_map_seed(stats_repo: str) -> None:
    _ = stats_repo
    referee = _StubReferee()
    commissioner = _StubCommissioner(season_id=uuid4())
    season_id: UUID
    env_id: UUID

    async with db_session() as session:
        season = Season(name=f"missing-seed-{uuid4().hex[:8]}", canonical=True, compat_version="0.5")
        session.add(season)
        await session.flush()
        season_id = season.id

        invalid_config = referee.make_env(seed=0).model_dump(mode="json")
        del invalid_config["game"]["map_builder"]["seed"]
        env_hash = hashlib.sha256(json.dumps(invalid_config, sort_keys=True).encode()).hexdigest()
        env_row = MettagridEnvConfig(
            config_hash=env_hash,
            config=invalid_config,
            name=referee.env_name,
            compat_version="0.5",
            num_agents=referee.num_agents,
        )
        session.add(env_row)
        await session.flush()
        env_id = env_row.id
        session.add(Pool(season_id=season.id, name="pool-1", env_config_id=env_row.id))
        await session.commit()

    async with db_session() as session:
        season = (await session.execute(select(Season).where(Season.id == season_id))).scalar_one()
        pools = await commissioner._ensure_pools_exist(season, {"pool-1": referee})
        pool = pools["pool-1"]
        assert pool.env_config is not None
        assert pool.env_config.id == env_id
