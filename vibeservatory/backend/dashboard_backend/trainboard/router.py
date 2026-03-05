from __future__ import annotations

import mimetypes
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

TRAINBOARD_BASE_PATH = "/train-board"

REPO_ROOT = Path(__file__).resolve().parents[4]
TRAINBOARD_SRC_ROOT = REPO_ROOT / "trainboard" / "src"
if str(TRAINBOARD_SRC_ROOT) not in sys.path:
    sys.path.append(str(TRAINBOARD_SRC_ROOT))

from metta.trainingboard.local.backend import server as trainboard_server  # noqa: E402


def _load_frontend_asset(file_name: str, *, is_static: bool) -> tuple[bytes, str]:
    base = trainboard_server.FRONTEND_ROOT / ("static" if is_static else "templates")
    target = trainboard_server._resolve_frontend_target(base, file_name)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="Missing file")

    mime_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    body = target.read_bytes()
    if not is_static and file_name == "index.html":
        body = body.decode("utf-8").replace("__TRAINBOARD_BASE_PATH__", TRAINBOARD_BASE_PATH).encode("utf-8")
        mime_type = "text/html; charset=utf-8"
    return body, mime_type


def _query_int(value: str | None, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def create_trainboard_router() -> APIRouter:
    router = APIRouter(prefix=TRAINBOARD_BASE_PATH, tags=["dashboard"])

    @router.get("", include_in_schema=False)
    @router.get("/", include_in_schema=False)
    async def trainboard_index() -> Response:
        body, content_type = _load_frontend_asset("index.html", is_static=False)
        return Response(content=body, media_type=content_type)

    @router.get("/static/{file_name:path}", include_in_schema=False)
    async def trainboard_static(file_name: str) -> Response:
        body, content_type = _load_frontend_asset(file_name, is_static=True)
        return Response(content=body, media_type=content_type)

    @router.get("/api/health")
    async def trainboard_health() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/api/v1/dashboard")
    async def trainboard_dashboard() -> dict[str, Any]:
        state_dir = Path(trainboard_server.DEFAULT_STATE_DIR).expanduser()
        return trainboard_server.build_dashboard_for_state_dir(state_dir)

    @router.get("/api/v1/task-ranking")
    async def trainboard_task_ranking(
        limit: str | None = Query(default=None),
        top_n: str | None = Query(default=None),
    ) -> dict[str, Any]:
        state_dir = Path(trainboard_server.DEFAULT_STATE_DIR).expanduser()
        resolved_limit = _query_int(limit, default=60, minimum=0, maximum=1000)
        resolved_top_n = _query_int(top_n, default=10, minimum=0, maximum=100)
        return trainboard_server.build_task_ranking_for_state_dir(
            state_dir,
            limit=resolved_limit,
            leaderboard_top_n=resolved_top_n,
        )

    @router.get("/api/v1/board")
    async def trainboard_board() -> dict[str, Any]:
        state_dir = Path(trainboard_server.DEFAULT_STATE_DIR).expanduser()
        return trainboard_server.build_board_payload_for_state_dir(state_dir)

    @router.post("/api/v1/recompute")
    async def trainboard_recompute(_: dict[str, Any] | None = None) -> dict[str, Any]:
        state_dir = Path(trainboard_server.DEFAULT_STATE_DIR).expanduser()
        return trainboard_server.build_board_payload_for_state_dir(state_dir)

    return router
