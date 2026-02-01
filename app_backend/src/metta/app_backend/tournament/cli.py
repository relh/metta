import asyncio

from metta.app_backend.health_server import start_health_server
from metta.app_backend.tournament.registry import SEASONS
from metta.common.otel.tracing import init_otel_tracing
from metta.common.util.log_config import init_logging, suppress_noisy_logs


def run_commissioner():
    start_health_server(port=8081)

    async def run_all() -> None:
        commissioners = [cls() for cls in SEASONS.values()]
        await asyncio.gather(*[c.run() for c in commissioners])

    asyncio.run(run_all())


def roll_season(season_name: str) -> None:
    from metta.app_backend.database import db_session
    from metta.app_backend.tournament.scripts.roll_season import roll_season_version

    commissioner_cls = SEASONS.get(season_name)
    if not commissioner_cls:
        raise ValueError(f"Unknown season '{season_name}', expected one of {list(SEASONS.keys())}")
    entry_pool = commissioner_cls().entry_pool

    async def run() -> None:
        async with db_session() as session:
            new_season = await roll_season_version(session, season_name, entry_pool)
            print(f"Rolled {season_name} to v{new_season.version}")

    asyncio.run(run())


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    init_otel_tracing(service_name="tournament-runner")
    run_commissioner()
