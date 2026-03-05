from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from metta.app_backend.routes.role_stats_routes import create_role_stats_router
from vibeservatory.backend.dashboard_backend.bardo.router import create_bardo_router
from vibeservatory.backend.dashboard_backend.cogames_diagnose.router import create_cogames_diagnose_router
from vibeservatory.backend.dashboard_backend.config import settings
from vibeservatory.backend.dashboard_backend.database import configure_dashboard_db
from vibeservatory.backend.dashboard_backend.state_page.router import create_dashboard_router


def create_app() -> FastAPI:
    configure_dashboard_db()

    app = FastAPI(
        title="Dashboard API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    cors_origins = [origin.strip() for origin in settings.DASHBOARD_CORS_ORIGINS.split(",") if origin.strip()]
    allow_all = settings.DASHBOARD_CORS_ORIGINS.strip() == "*" or "*" in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(create_dashboard_router())
    app.include_router(create_bardo_router())
    app.include_router(create_cogames_diagnose_router())
    app.include_router(create_role_stats_router())

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/internal/openapi.json", include_in_schema=False)
    async def internal_openapi() -> JSONResponse:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        return JSONResponse(schema)

    @app.get("/internal/docs", include_in_schema=False)
    async def internal_docs():
        return get_swagger_ui_html(openapi_url="/internal/openapi.json", title=f"{app.title} Internal Docs")

    return app


app = create_app()
