import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from metta.app_backend.database import db_session
from metta.app_backend.health_server import start_health_server, update_heartbeat
from metta.app_backend.models.tournament import Season
from metta.app_backend.otel.metrics import init_meter_provider
from metta.app_backend.tournament.commissioners.factory import build_commissioner
from metta.app_backend.tournament.registry import SEASONS
from metta.app_backend.tournament.season_resolver import get_or_create_season
from metta.app_backend.tournament.settings import POLL_INTERVAL_SECONDS
from metta.common.otel.tracing import init_otel_tracing
from metta.common.util.log_config import init_logging, suppress_noisy_logs

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 10


async def _heartbeat_loop() -> None:
    while True:
        update_heartbeat()
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def _query_live_seasons(session: AsyncSession) -> list[Season]:
    result = await session.execute(
        select(Season).where(col(Season.canonical).is_(True), Season.disabled_at.is_(None))  # type: ignore[union-attr]
    )
    return list(result.scalars().all())


async def _seed_missing_seasons() -> None:
    async with db_session() as session:
        for commissioner_cls in SEASONS.values():
            await get_or_create_season(session, commissioner_cls)
        await session.commit()


async def _supervisor_loop() -> None:
    await _seed_missing_seasons()
    tasks: dict[UUID, asyncio.Task[None]] = {}
    while True:
        async with db_session() as session:
            live_seasons = await _query_live_seasons(session)

        done_ids = [sid for sid, task in tasks.items() if task.done()]
        for sid in done_ids:
            task = tasks.pop(sid)
            if task.cancelled():
                logger.info(f"Commissioner for season {sid} was cancelled")
            elif task.exception():
                logger.error(f"Commissioner for season {sid} crashed", exc_info=task.exception())
            else:
                logger.info(f"Commissioner for season {sid} exited cleanly")

        for season in live_seasons:
            if season.id in tasks:
                continue
            if season.name not in SEASONS:
                logger.warning(f"Season '{season.name}' not in SEASONS registry, skipping")
                continue
            commissioner = await build_commissioner(season.name, season_id=season.id)
            tasks[season.id] = asyncio.create_task(commissioner.run())

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def run_commissioner() -> None:
    start_health_server(port=8081)

    async def _main() -> None:
        await asyncio.gather(_heartbeat_loop(), _supervisor_loop())

    asyncio.run(_main())


def roll_season(season_name: str, *, compat_version: str | None = None) -> None:
    from metta.app_backend.tournament.scripts.roll_season import roll_season as roll_season_script  # noqa: PLC0415

    roll_season_script(season_name, compat_version=compat_version)


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    init_meter_provider()
    init_otel_tracing(service_name="tournament-runner")
    run_commissioner()
