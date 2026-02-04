import pytest
from sqlmodel import select

from metta.app_backend.database import db_session
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.tournament.scripts.roll_season import roll_season_version
from metta.app_backend.tournament.season_resolver import resolve_season


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
        season_v2 = await roll_season_version(session, "integration-test", entry_pool="qualifying")
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
