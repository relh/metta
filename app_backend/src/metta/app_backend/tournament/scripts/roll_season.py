# pyright: reportArgumentType=false
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from metta.app_backend.models.tournament import (
    MembershipAction,
    MembershipChange,
    Pool,
    PoolPlayer,
    Season,
)

logger = logging.getLogger(__name__)


async def roll_season_version(session: AsyncSession, season_name: str) -> Season:
    old_season = (
        await session.execute(
            select(Season)
            .where(Season.name == season_name, col(Season.canonical).is_(True))
            .options(selectinload(Season.pools))
        )
    ).scalar_one_or_none()

    if not old_season:
        raise ValueError(f"No canonical season found for '{season_name}'")

    old_season.disabled_at = datetime.now(UTC)
    old_season.canonical = False

    new_season = Season(
        name=season_name,
        version=old_season.version + 1,
        canonical=True,
        disabled_at=None,
    )
    session.add(new_season)
    await session.flush()

    pool_mapping: dict[str, Pool] = {}
    for old_pool in old_season.pools:
        new_pool = Pool(
            season_id=new_season.id,
            name=old_pool.name,
        )
        session.add(new_pool)
        if old_pool.name:
            pool_mapping[old_pool.name] = new_pool

    await session.flush()

    logger.info(f"Rolled season '{season_name}' from v{old_season.version} to v{new_season.version}")

    for old_pool in old_season.pools:
        if not old_pool.name or old_pool.name not in pool_mapping:
            continue

        new_pool = pool_mapping[old_pool.name]
        active_players = (
            (
                await session.execute(
                    select(PoolPlayer).where(PoolPlayer.pool_id == old_pool.id, col(PoolPlayer.retired).is_(False))
                )
            )
            .scalars()
            .all()
        )

        for old_player in active_players:
            new_player = PoolPlayer(
                pool_id=new_pool.id,
                policy_version_id=old_player.policy_version_id,
                retired=False,
            )
            session.add(new_player)
            await session.flush()

            session.add(
                MembershipChange(
                    pool_player_id=new_player.id,
                    action=MembershipAction.add,
                    notes=f"Migrated from v{old_season.version}",
                )
            )

        logger.info(f"Migrated {len(active_players)} active members to pool '{old_pool.name}'")

    await session.commit()
    return new_season
