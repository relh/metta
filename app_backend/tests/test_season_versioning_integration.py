import pytest
from sqlmodel import select

from metta.app_backend.database import db_session
from metta.app_backend.metta_repo import MettaRepo
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.tournament.scripts.roll_season import roll_season_version
from metta.app_backend.tournament.season_resolver import resolve_season


@pytest.mark.asyncio
async def test_season_version_flow(isolated_stats_repo: MettaRepo) -> None:  # noqa: ARG001
    async with db_session() as session:
        season_v1 = Season(name="integration-test", version=1, canonical=True)
        session.add(season_v1)
        await session.flush()

        pool = Pool(season_id=season_v1.id, name="competition")
        session.add(pool)
        await session.flush()

        active_policy = Policy(name="active-policy", user_id="test-user")
        session.add(active_policy)
        await session.flush()
        active_pv = PolicyVersion(policy_id=active_policy.id, version=1)
        session.add(active_pv)
        await session.flush()
        session.add(PoolPlayer(pool_id=pool.id, policy_version_id=active_pv.id, retired=False))

        retired_policy = Policy(name="retired-policy", user_id="test-user")
        session.add(retired_policy)
        await session.flush()
        retired_pv = PolicyVersion(policy_id=retired_policy.id, version=1)
        session.add(retired_pv)
        await session.flush()
        session.add(PoolPlayer(pool_id=pool.id, policy_version_id=retired_pv.id, retired=True))

        season_v1_id = season_v1.id
        active_pv_id = active_pv.id

    async with db_session() as session:
        season_v2 = await roll_season_version(session, "integration-test")
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
        assert len(new_pools) == 1
        new_players = (
            (await session.execute(select(PoolPlayer).where(PoolPlayer.pool_id == new_pools[0].id))).scalars().all()
        )
        assert len(new_players) == 1
        assert new_players[0].policy_version_id == active_pv_id

    async with db_session() as session:
        with pytest.raises(ValueError, match="No canonical season found"):
            await roll_season_version(session, "nonexistent-season")
