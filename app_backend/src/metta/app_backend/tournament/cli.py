import asyncio

from metta.app_backend.database import db_session
from metta.app_backend.health_server import start_health_server, update_heartbeat
from metta.app_backend.models.tournament import Season
from metta.app_backend.tournament.commissioners.base import CommissionerBase
from metta.app_backend.tournament.commissioners.factory import initialize_commissioner
from metta.app_backend.tournament.registry import SEASONS
from metta.app_backend.tournament.season_resolver import resolve_season
from metta.common.otel.tracing import init_otel_tracing
from metta.common.util.log_config import init_logging, suppress_noisy_logs

HEARTBEAT_INTERVAL_SECONDS = 10


async def _heartbeat_loop() -> None:
    while True:
        update_heartbeat()
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def _build_commissioners() -> list[CommissionerBase]:
    commissioners: list[CommissionerBase] = []
    async with db_session() as session:
        for commissioner_cls in SEASONS.values():
            initial_fields = commissioner_cls.get_initial_season_fields()
            season = await resolve_season(session, commissioner_cls.season_name)
            if season is None:
                season = Season(
                    name=commissioner_cls.season_name,
                    canonical=True,
                    compat_version=commissioner_cls.initial_compat_version,
                    **initial_fields,
                )
                session.add(season)
                await session.flush()
            else:
                updated = False
                for field_name, field_value in initial_fields.items():
                    if getattr(season, field_name) is None:
                        setattr(season, field_name, field_value)
                        updated = True
                if updated:
                    await session.flush()
            commissioner = commissioner_cls(season_id=season.id)
            await initialize_commissioner(commissioner)
            commissioners.append(commissioner)

    return commissioners


def run_commissioner():
    start_health_server(port=8081)

    async def run_all() -> None:
        commissioners = await _build_commissioners()
        await asyncio.gather(_heartbeat_loop(), *[c.run() for c in commissioners])

    asyncio.run(run_all())


def roll_season(season_name: str, *, compat_version: str | None = None) -> None:
    from metta.app_backend.tournament.scripts.roll_season import roll_season as roll_season_script  # noqa: PLC0415

    roll_season_script(season_name, compat_version=compat_version)


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    init_otel_tracing(service_name="tournament-runner")
    run_commissioner()
