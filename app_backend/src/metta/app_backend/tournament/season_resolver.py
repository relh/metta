from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from metta.app_backend.models.tournament import Season

if TYPE_CHECKING:
    from metta.app_backend.tournament.commissioners.base import CommissionerBase

logger = logging.getLogger(__name__)


def parse_season_ref(season_ref: str) -> tuple[str, int | None]:
    if ":v" in season_ref:
        name, version_str = season_ref.rsplit(":v", 1)
        try:
            return name, int(version_str)
        except ValueError:
            return season_ref, None
    if ":" in season_ref:
        name, version_str = season_ref.rsplit(":", 1)
        try:
            return name, int(version_str)
        except ValueError:
            return season_ref, None
    return season_ref, None


async def resolve_season(
    session: AsyncSession,
    name: str,
    version: int | None = None,
) -> Season | None:
    if version is not None:
        result = await session.execute(select(Season).where(Season.name == name, Season.version == version))
        return result.scalar_one_or_none()
    result = await session.execute(select(Season).where(Season.name == name, col(Season.canonical).is_(True)))
    return result.scalar_one_or_none()


async def get_or_create_season(
    session: AsyncSession,
    commissioner_cls: type[CommissionerBase],
) -> Season:
    existing = await resolve_season(session, commissioner_cls.season_name)
    if existing:
        return existing
    initial_fields: dict[str, Any] = commissioner_cls.get_initial_season_fields()
    season = Season(
        name=commissioner_cls.season_name,
        canonical=True,
        compat_version=commissioner_cls.initial_compat_version,
        **initial_fields,
    )
    session.add(season)
    await session.flush()
    logger.info(f"Seeded missing season '{commissioner_cls.season_name}'")
    return season


async def get_season_versions(session: AsyncSession, name: str) -> list[Season]:
    result = await session.execute(select(Season).where(Season.name == name).order_by(col(Season.version).desc()))
    return list(result.scalars().all())
