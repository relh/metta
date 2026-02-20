import pytest
from sqlmodel import select

from metta.app_backend.database import db_session
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.tournament.commissioners.teams.config import (
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
    TeamTournamentConfig,
)
from metta.app_backend.tournament.scripts.roll_season import roll_season_version
from metta.app_backend.tournament.season_resolver import resolve_season


def _test_team_config(top_k: int) -> dict[str, object]:
    return TeamTournamentConfig(
        stages=[
            PolicyEvalStage(policies_per_team=1),
            SampleStage(team_size=8, num_teams=32),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=top_k),
        ]
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_season_compat_version_nullable(stats_repo: str) -> None:  # noqa: ARG001
    async with db_session() as session:
        season = Season(name="test-compat", canonical=True, compat_version="0.4")
        session.add(season)
        await session.flush()
        result = await session.execute(select(Season).where(Season.name == "test-compat"))
        s = result.scalar_one()
        assert s.compat_version == "0.4"


@pytest.mark.asyncio
async def test_season_compat_version_null_default(stats_repo: str) -> None:  # noqa: ARG001
    async with db_session() as session:
        season = Season(name="test-no-compat", canonical=True)
        session.add(season)
        await session.flush()
        result = await session.execute(select(Season).where(Season.name == "test-no-compat"))
        s = result.scalar_one()
        assert s.compat_version is None


@pytest.mark.asyncio
async def test_season_version_flow(stats_repo: str) -> None:  # noqa: ARG001
    async with db_session() as session:
        season_v1 = Season(name="integration-test", version=1, canonical=True)
        session.add(season_v1)
        await session.flush()

        qualifying = Pool(season_id=season_v1.id, name="qualifying")
        competition = Pool(season_id=season_v1.id, name="competition")
        session.add(qualifying)
        session.add(competition)
        await session.flush()

        policy_a = Policy(name="policy-a", user_id="test-user")
        policy_b = Policy(name="policy-b", user_id="test-user")
        retired_policy = Policy(name="retired-policy", user_id="test-user")
        session.add_all([policy_a, policy_b, retired_policy])
        await session.flush()
        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        retired_pv = PolicyVersion(policy_id=retired_policy.id, version=1)
        session.add_all([pv_a, pv_b, retired_pv])
        await session.flush()

        session.add(PoolPlayer(pool_id=qualifying.id, policy_version_id=pv_a.id, retired=False))
        session.add(PoolPlayer(pool_id=competition.id, policy_version_id=pv_b.id, retired=False))
        session.add(PoolPlayer(pool_id=competition.id, policy_version_id=retired_pv.id, retired=True))

        season_v1_id = season_v1.id
        active_pv_ids = {pv_a.id, pv_b.id}

    async with db_session() as session:
        season_v2 = await roll_season_version(
            session, "integration-test", entry_pool="qualifying", migrate_members=True
        )
        assert season_v2.version == 2
        assert season_v2.canonical is True
        season_v2_id = season_v2.id

    async with db_session() as session:
        old = (await session.execute(select(Season).where(Season.id == season_v1_id))).scalar_one()
        assert old.disabled_at is not None
        assert old.canonical is False

    async with db_session() as session:
        assert (await resolve_season(session, "integration-test")).id == season_v2_id  # type: ignore[union-attr]
        assert (await resolve_season(session, "integration-test", version=1)).id == season_v1_id  # type: ignore[union-attr]

    async with db_session() as session:
        new_pools = (await session.execute(select(Pool).where(Pool.season_id == season_v2_id))).scalars().all()
        assert len(new_pools) == 2

        entry = next(p for p in new_pools if p.name == "qualifying")
        comp = next(p for p in new_pools if p.name == "competition")

        entry_players = (
            (await session.execute(select(PoolPlayer).where(PoolPlayer.pool_id == entry.id))).scalars().all()
        )
        assert {p.policy_version_id for p in entry_players} == active_pv_ids

        comp_players = (await session.execute(select(PoolPlayer).where(PoolPlayer.pool_id == comp.id))).scalars().all()
        assert len(comp_players) == 0

    async with db_session() as session:
        with pytest.raises(ValueError, match="No canonical season found"):
            await roll_season_version(session, "nonexistent-season", entry_pool="qualifying")


@pytest.mark.asyncio
async def test_season_version_roll_without_pool_copy(stats_repo: str) -> None:  # noqa: ARG001
    async with db_session() as session:
        season_v1 = Season(name="integration-test-no-copy", version=1, canonical=True)
        session.add(season_v1)
        await session.flush()

        stage_1 = Pool(season_id=season_v1.id, name="stage-1")
        stage_2 = Pool(season_id=season_v1.id, name="stage-2")
        team_round_1 = Pool(season_id=season_v1.id, name="team-round-1")
        session.add_all([stage_1, stage_2, team_round_1])
        await session.flush()

        policy_a = Policy(name="policy-a-no-copy", user_id="test-user")
        policy_b = Policy(name="policy-b-no-copy", user_id="test-user")
        retired_policy = Policy(name="retired-policy-no-copy", user_id="test-user")
        session.add_all([policy_a, policy_b, retired_policy])
        await session.flush()

        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        retired_pv = PolicyVersion(policy_id=retired_policy.id, version=1)
        session.add_all([pv_a, pv_b, retired_pv])
        await session.flush()

        session.add(PoolPlayer(pool_id=stage_1.id, policy_version_id=pv_a.id, retired=False))
        session.add(PoolPlayer(pool_id=stage_2.id, policy_version_id=pv_b.id, retired=False))
        session.add(PoolPlayer(pool_id=team_round_1.id, policy_version_id=retired_pv.id, retired=True))

        active_pv_ids = {pv_a.id, pv_b.id}

    async with db_session() as session:
        season_v2 = await roll_season_version(
            session,
            "integration-test-no-copy",
            entry_pool="stage-1",
            migrate_members=True,
            copy_existing_pools=False,
        )
        season_v2_id = season_v2.id

    async with db_session() as session:
        pools = (await session.execute(select(Pool).where(Pool.season_id == season_v2_id))).scalars().all()
        assert len(pools) == 1
        assert pools[0].name == "stage-1"

        entry_players = (
            (await session.execute(select(PoolPlayer).where(PoolPlayer.pool_id == pools[0].id))).scalars().all()
        )
        assert {p.policy_version_id for p in entry_players} == active_pv_ids


@pytest.mark.asyncio
async def test_roll_season_copies_team_tournament_config_by_default(stats_repo: str) -> None:  # noqa: ARG001
    source_config = _test_team_config(top_k=3)
    season_name = "integration-test-team-config-copy"

    async with db_session() as session:
        season_v1 = Season(
            name=season_name,
            version=1,
            canonical=True,
            team_tournament_config=source_config,
        )
        session.add(season_v1)
        await session.flush()
        session.add(Pool(season_id=season_v1.id, name="stage-1"))

    async with db_session() as session:
        season_v2 = await roll_season_version(
            session,
            season_name,
            entry_pool="stage-1",
            copy_existing_pools=False,
        )
        assert season_v2.team_tournament_config == source_config


@pytest.mark.asyncio
async def test_roll_season_allows_team_tournament_config_override(stats_repo: str) -> None:  # noqa: ARG001
    source_config = _test_team_config(top_k=2)
    override_config = _test_team_config(top_k=7)
    season_name = "integration-test-team-config-override"

    async with db_session() as session:
        season_v1 = Season(
            name=season_name,
            version=1,
            canonical=True,
            team_tournament_config=source_config,
        )
        session.add(season_v1)
        await session.flush()
        session.add(Pool(season_id=season_v1.id, name="stage-1"))

    async with db_session() as session:
        season_v2 = await roll_season_version(
            session,
            season_name,
            entry_pool="stage-1",
            copy_existing_pools=False,
            team_tournament_config=override_config,
        )
        assert season_v2.team_tournament_config == override_config
