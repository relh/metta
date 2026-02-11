#!/usr/bin/env -S uv run
# need this to import and call suppress_noisy_logs first
# ruff: noqa: E402

from metta.common.util.log_config import suppress_noisy_logs

suppress_noisy_logs()

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import fastapi
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.middleware.cors import CORSMiddleware
from pydantic.main import BaseModel

from metta.app_backend.auth import get_user
from metta.app_backend.config import settings
from metta.app_backend.routes import (
    eval_task_routes,
    job_routes,
    smart_plug_routes,
    sql_routes,
    stats_routes,
    sweep_routes,
    tournament_routes,
)


class WhoAmIResponse(BaseModel):
    user_email: str


_logging_configured = False


class NoWhoAmIFilter(logging.Filter):
    """Filter out /whoami requests from uvicorn access logs."""

    def filter(self, record):
        # Filter out /whoami requests from uvicorn access logs
        if hasattr(record, "getMessage"):
            message = record.getMessage()
            return not ("/whoami" in message and "GET" in message)
        return True


def setup_logging():
    """Configure logging for the application, including scorecard performance logging."""
    global _logging_configured

    if _logging_configured:
        return

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Configure scorecard performance logger specifically
    scorecard_logger = logging.getLogger("dashboard_performance")
    scorecard_logger.setLevel(logging.INFO)

    # Configure database query performance logger
    db_logger = logging.getLogger("db_performance")
    db_logger.setLevel(logging.INFO)

    # Configure route performance logger
    route_logger = logging.getLogger("route_performance")
    route_logger.setLevel(logging.INFO)

    # Configure scorecard logger
    scorecard_routes_logger = logging.getLogger("policy_scorecard_routes")
    scorecard_routes_logger.setLevel(logging.INFO)

    # Configure psycopg pool logger
    psycopg_pool_logger = logging.getLogger("psycopg.pool")
    psycopg_pool_logger.setLevel(logging.WARNING)

    # Ensure the loggers don't duplicate messages from root logger
    scorecard_logger.propagate = True
    db_logger.propagate = True
    route_logger.propagate = True
    scorecard_routes_logger.propagate = True

    # Filter out /whoami requests from uvicorn access logs
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.addFilter(NoWhoAmIFilter())

    _logging_configured = True
    print(
        "Logging configured - performance logging enabled (routes, db queries, scorecards), /whoami requests filtered"
    )


def create_app() -> fastapi.FastAPI:
    setup_logging()

    @asynccontextmanager
    async def lifespan(_: fastapi.FastAPI):
        if settings.RUN_MIGRATIONS:
            alembic_cfg = Config(str(Path(__file__).parent.parent.parent.parent / "alembic.ini"))
            alembic_cfg.config_file_name = None  # prevent fileConfig from resetting app loggers
            command.upgrade(alembic_cfg, "head")
        yield

    app = fastapi.FastAPI(lifespan=lifespan)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "https://observatory.softmax-research.net",
        ],  # Frontend URLs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create routers with the provided StatsRepo
    eval_task_router = eval_task_routes.create_eval_task_router()
    sql_router = sql_routes.create_sql_router()
    stats_router = stats_routes.create_stats_router()
    sweep_router = sweep_routes.create_sweep_router()
    jobs_router = job_routes.create_job_router()
    tournament_router = tournament_routes.create_tournament_router()
    smart_plug_router = smart_plug_routes.create_smart_plug_router()

    app.include_router(eval_task_router)
    app.include_router(sql_router)
    app.include_router(stats_router)
    app.include_router(sweep_router)
    app.include_router(jobs_router)
    app.include_router(tournament_router)
    app.include_router(smart_plug_router)

    @app.get("/whoami")
    async def whoami(request: fastapi.Request) -> WhoAmIResponse:
        user = await get_user(request)
        return WhoAmIResponse(user_email=user.email if user else "unknown")

    return app


if __name__ == "__main__":
    app = create_app()

    async def main():
        config = uvicorn.Config(app, host=settings.HOST, port=settings.PORT)
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(main())
