# pyright: reportArgumentType=false
import argparse
import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

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


async def roll_season_version(
    session: AsyncSession,
    season_name: str,
    entry_pool: str,
    *,
    migrate_members: bool = False,
    overrides: dict[str, str | None] | None = None,
) -> Season:
    old_season = (
        await session.execute(
            select(Season)
            .where(Season.name == season_name, col(Season.canonical).is_(True))
            .options(selectinload(Season.pools))
        )
    ).scalar_one_or_none()

    if not old_season:
        raise ValueError(f"No canonical season found for '{season_name}'")

    overrides = overrides or {}
    compat_version = overrides["compat_version"] if "compat_version" in overrides else old_season.compat_version

    old_season.disabled_at = datetime.now(UTC)
    old_season.canonical = False

    new_season = Season(
        name=season_name,
        version=old_season.version + 1,
        canonical=True,
        disabled_at=None,
        compat_version=compat_version,
    )
    session.add(new_season)
    await session.flush()

    new_entry_pool: Pool | None = None
    for old_pool in old_season.pools:
        new_pool = Pool(season_id=new_season.id, name=old_pool.name)
        session.add(new_pool)
        if old_pool.name == entry_pool:
            new_entry_pool = new_pool

    await session.flush()

    if new_entry_pool is None:
        raise ValueError(f"Entry pool '{entry_pool}' not found in season '{season_name}'")

    logger.info(f"Rolled season '{season_name}' from v{old_season.version} to v{new_season.version}")

    if migrate_members:
        active_policy_ids: set[UUID] = set()
        for old_pool in old_season.pools:
            players = (
                (
                    await session.execute(
                        select(PoolPlayer).where(PoolPlayer.pool_id == old_pool.id, col(PoolPlayer.retired).is_(False))
                    )
                )
                .scalars()
                .all()
            )
            for p in players:
                active_policy_ids.add(p.policy_version_id)

        for policy_version_id in active_policy_ids:
            new_player = PoolPlayer(
                pool_id=new_entry_pool.id,
                policy_version_id=policy_version_id,
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

        logger.info(f"Migrated {len(active_policy_ids)} active members to entry pool '{entry_pool}'")
    else:
        logger.info("Skipped member migration")

    await session.commit()
    return new_season


def main() -> None:
    from metta.app_backend.database import db_session  # noqa: PLC0415
    from metta.app_backend.tournament.registry import SEASONS  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Roll a tournament season to a new version")
    parser.add_argument("season_name", help=f"Season to roll (one of {list(SEASONS.keys())})")
    parser.add_argument("--migrate-players", action="store_true", help="Migrate active players to the new season")
    parser.add_argument("--compat-version", help="Set compat version on the new season (default: carry forward)")
    args = parser.parse_args()

    commissioner_cls = SEASONS.get(args.season_name)
    if not commissioner_cls:
        parser.error(f"Unknown season '{args.season_name}', expected one of {list(SEASONS.keys())}")
    entry_pool = commissioner_cls().entry_pool

    overrides: dict[str, str | None] = {}
    if args.compat_version is not None:
        overrides["compat_version"] = args.compat_version

    async def run() -> None:
        async with db_session() as session:
            new_season = await roll_season_version(
                session,
                args.season_name,
                entry_pool,
                migrate_members=args.migrate_players,
                overrides=overrides,
            )
            print(f"Rolled {args.season_name} to v{new_season.version} (compat={new_season.compat_version})")

    asyncio.run(run())


if __name__ == "__main__":
    main()
