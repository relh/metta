from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from metta.app_backend.models.tournament import Season


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


async def get_season_versions(session: AsyncSession, name: str) -> list[Season]:
    result = await session.execute(select(Season).where(Season.name == name).order_by(col(Season.version).desc()))
    return list(result.scalars().all())
