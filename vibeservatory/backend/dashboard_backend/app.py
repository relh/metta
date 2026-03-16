import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from vibeservatory.backend.dashboard_backend.auth import SoftmaxUser
from vibeservatory.backend.dashboard_backend.bardo.router import create_bardo_router
from vibeservatory.backend.dashboard_backend.chatprop.router import create_chatprop_router
from vibeservatory.backend.dashboard_backend.config import settings
from vibeservatory.backend.dashboard_backend.database import configure_dashboard_db
from vibeservatory.backend.dashboard_backend.diagnose.router import create_diagnose_router
from vibeservatory.backend.dashboard_backend.pantheon.router import create_pantheon_router
from vibeservatory.backend.dashboard_backend.policy_dashboard.router import create_policy_dashboard_router
from vibeservatory.backend.dashboard_backend.role_stats.router import create_role_stats_router
from vibeservatory.backend.dashboard_backend.trainboard.router import create_trainboard_router


def _load_required_route_paths_from_contract() -> frozenset[str]:
    contract_path = Path(__file__).resolve().parents[2] / "iframe_surfaces.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Invalid iframe surface contract payload in {contract_path}")
    required_routes = {
        entry["backend_required_route"]
        for entry in payload
        if isinstance(entry, dict) and isinstance(entry.get("backend_required_route"), str)
    }
    if not required_routes:
        raise RuntimeError(f"No backend_required_route entries found in {contract_path}")
    return frozenset(required_routes)


REQUIRED_ROUTE_PATHS = _load_required_route_paths_from_contract()
SURFACE_ROUTER_FACTORIES = (
    create_policy_dashboard_router,
    create_bardo_router,
    create_pantheon_router,
    create_chatprop_router,
    create_trainboard_router,
    create_diagnose_router,
)


def _assert_required_routes(app: FastAPI) -> None:
    route_paths = {route.path for route in app.routes}
    missing_routes = sorted(REQUIRED_ROUTE_PATHS - route_paths)
    if missing_routes:
        raise RuntimeError(f"Dashboard app missing required routes: {', '.join(missing_routes)}")


def create_app() -> FastAPI:
    configure_dashboard_db()

    app = FastAPI(
        title="Vibeservatory Surface API",
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
    app.add_middleware(GZipMiddleware, minimum_size=settings.DASHBOARD_GZIP_MIN_SIZE)

    # The six embedded Vibeservatory surfaces are peer services. Each owns its
    # own route namespace and frontend host path, while sharing this backend app.
    for router_factory in SURFACE_ROUTER_FACTORIES:
        app.include_router(router_factory())
    app.include_router(create_role_stats_router())
    _assert_required_routes(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/internal/openapi.json", include_in_schema=False)
    async def internal_openapi(_user: SoftmaxUser) -> JSONResponse:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        return JSONResponse(schema)

    @app.get("/internal/docs", include_in_schema=False)
    async def internal_docs(_user: SoftmaxUser):
        return get_swagger_ui_html(openapi_url="/internal/openapi.json", title=f"{app.title} Internal Docs")

    return app


app = create_app()
