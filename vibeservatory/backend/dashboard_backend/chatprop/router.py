from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from vibeservatory.backend.dashboard_backend.auth import SoftmaxUser
from vibeservatory.backend.dashboard_backend.local_package_bootstrap import ensure_repo_src_on_path

CHATPROP_SRC_ROOT = ensure_repo_src_on_path("chatprop/src")

from metta.chatprop.config import load_config  # noqa: E402
from metta.chatprop.local.backend import server as chatprop_server  # noqa: E402
from metta.chatprop.local.backend.server import FRONTEND_ROOT  # noqa: E402
from metta.chatprop.local.flowchart import write_flowchart_outputs  # noqa: E402
from metta.chatprop.scanner import find_transcripts_for_branches  # noqa: E402

CHATPROP_BASE_PATH = "/chatprop"


def _load_frontend_asset(file_name: str, *, is_static: bool) -> tuple[bytes, str]:
    base = FRONTEND_ROOT / ("static" if is_static else "templates")
    target = chatprop_server._resolve_frontend_target(base, file_name)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="Missing file")

    mime_type, _ = mimetypes.guess_type(str(target))
    body = target.read_bytes()
    if not is_static and file_name == "index.html":
        body = body.decode("utf-8").replace("__CHATPROP_BASE_PATH__", CHATPROP_BASE_PATH).encode("utf-8")
    return body, (mime_type or "text/plain")


def _extract_branches_or_400(payload: dict[str, Any]) -> list[str]:
    branches = chatprop_server._extract_branches(payload)
    if not branches:
        raise HTTPException(status_code=400, detail="branches must be a non-empty list of strings")
    return branches


def _resolve_flowchart_graph_or_400(
    graph_raw: Any,
    *,
    config: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if graph_raw is not None and not isinstance(graph_raw, dict):
        raise HTTPException(status_code=400, detail="workflow_graph must be an object")

    workflow_graph = graph_raw
    catalog: dict[str, Any] | None = None
    if workflow_graph is None:
        resolved_config = config or load_config()
        catalog = chatprop_server._build_catalog(resolved_config, refresh=False)
        workflow_graph = catalog.get("workflow_graph")
        if not isinstance(workflow_graph, dict):
            raise HTTPException(status_code=500, detail="Catalog missing workflow graph")

    return workflow_graph, catalog


def create_chatprop_router() -> APIRouter:
    router = APIRouter(prefix=CHATPROP_BASE_PATH, tags=["chatprop"])

    @router.get("", include_in_schema=False)
    @router.get("/", include_in_schema=False)
    async def chatprop_index() -> Response:
        body, content_type = _load_frontend_asset("index.html", is_static=False)
        return Response(content=body, media_type=content_type)

    @router.get("/static/{file_name:path}", include_in_schema=False)
    async def chatprop_static(file_name: str) -> Response:
        body, content_type = _load_frontend_asset(file_name, is_static=True)
        return Response(content=body, media_type=content_type)

    @router.get("/api/health")
    async def chatprop_health(_user: SoftmaxUser) -> dict[str, bool]:
        return {"ok": True}

    @router.get("/api/catalog")
    async def chatprop_catalog(_user: SoftmaxUser, refresh: str = Query(default="0")) -> dict[str, Any]:
        refresh_enabled = refresh in {"1", "true", "yes"}
        payload = chatprop_server._build_catalog(load_config(), refresh=refresh_enabled)
        return payload

    @router.post("/api/catalog/jobs")
    async def chatprop_catalog_job_create(
        _user: SoftmaxUser,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        refresh_enabled = payload.get("refresh") in {True, "1", "true", "yes"}
        return chatprop_server._create_catalog_job(bool(refresh_enabled))

    @router.get("/api/catalog/jobs/{job_id}")
    async def chatprop_catalog_job_status(job_id: str, _user: SoftmaxUser) -> dict[str, Any]:
        job = chatprop_server._get_catalog_job(job_id.strip())
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown catalog job")
        return job

    @router.post("/api/analysis/find")
    async def chatprop_analysis_find(
        _user: SoftmaxUser,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        branches = _extract_branches_or_400(payload)
        config = load_config()
        matches = find_transcripts_for_branches(config, branches)
        return {
            "branches": branches,
            "count": len(matches),
            "matches": [
                {
                    "path": str(match.path),
                    "source": match.source,
                    "session_id": match.session_id,
                    "size_bytes": match.size_bytes,
                    "matched_branches": match.matched_branches,
                }
                for match in matches
            ],
        }

    @router.post("/api/analysis/context")
    async def chatprop_analysis_context(
        _user: SoftmaxUser,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        branches = _extract_branches_or_400(payload)
        context = chatprop_server.build_analysis_context(branches, load_config())
        return {"branches": branches, "length": len(context), "context": context}

    @router.post("/api/analysis/run")
    async def chatprop_analysis_run(
        _user: SoftmaxUser,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        branches = _extract_branches_or_400(payload)
        output = chatprop_server.run_analysis(branches, load_config())
        if not output.strip():
            raise HTTPException(status_code=502, detail="analysis produced no output")
        return {"branches": branches, "output": output}

    @router.post("/api/flowchart/render")
    async def chatprop_flowchart_render(
        _user: SoftmaxUser,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        options = chatprop_server._flowchart_options_from_payload(payload)
        if options is None:
            raise HTTPException(status_code=400, detail="Invalid flowchart options")
        workflow_graph, catalog = _resolve_flowchart_graph_or_400(payload.get("workflow_graph"))
        return chatprop_server._flowchart_payload_with_catalog(workflow_graph, options=options, catalog=catalog)

    @router.post("/api/flowchart/save")
    async def chatprop_flowchart_save(
        _user: SoftmaxUser,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        options = chatprop_server._flowchart_options_from_payload(payload)
        if options is None:
            raise HTTPException(status_code=400, detail="Invalid flowchart options")

        config = load_config()
        workflow_graph, catalog = _resolve_flowchart_graph_or_400(payload.get("workflow_graph"), config=config)
        rendered = chatprop_server._flowchart_payload_with_catalog(workflow_graph, options=options, catalog=catalog)

        default_mermaid_path, default_json_path = chatprop_server._flowchart_export_defaults(config)
        mermaid_path_raw = payload.get("mermaid_path")
        json_path_raw = payload.get("json_path")

        mermaid_path = chatprop_server._parse_output_path(mermaid_path_raw)
        if mermaid_path is None:
            if mermaid_path_raw is not None and not (
                isinstance(mermaid_path_raw, str) and not mermaid_path_raw.strip()
            ):
                raise HTTPException(status_code=400, detail="mermaid_path must be a path string")
            mermaid_path = default_mermaid_path

        json_path = chatprop_server._parse_output_path(json_path_raw)
        if json_path is None:
            if json_path_raw is None:
                json_path = default_json_path
            elif not (isinstance(json_path_raw, str) and not json_path_raw.strip()):
                raise HTTPException(status_code=400, detail="json_path must be a path string")

        write_flowchart_outputs(payload=rendered, mermaid_path=mermaid_path, json_path=json_path)
        return {
            "saved": True,
            "mermaid_path": str(mermaid_path),
            "json_path": str(json_path) if json_path is not None else None,
            "node_count": rendered["selected_graph"]["node_count"],
            "edge_count": rendered["selected_graph"]["edge_count"],
            "generated_at": rendered["generated_at"],
        }

    return router
