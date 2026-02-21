import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from dashboard.backend.dashboard_backend.auth import SoftmaxUser
from dashboard.backend.dashboard_backend.config import settings
from metta.app_backend.route_logger import timed_http_handler

_RUN_ID_RE = re.compile(r"^(?!.*\.\.)[0-9A-Za-z._-]+$")
_REPO_SENTINEL = "pnpm-workspace.yaml"


class DiagnoseRunSummary(BaseModel):
    run_id: str
    manifest: dict[str, Any] | None


class DiagnoseRunsResponse(BaseModel):
    runs: list[DiagnoseRunSummary]


def _assert_safe_name(value: str, field_name: str) -> None:
    if not _RUN_ID_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: {value}")


def _content_type_for_artifact(artifact: str) -> str:
    if artifact.endswith(".json"):
        return "application/json; charset=utf-8"
    if artifact.endswith(".html"):
        return "text/html; charset=utf-8"
    if artifact.endswith(".md"):
        return "text/markdown; charset=utf-8"
    if artifact.endswith(".txt"):
        return "text/plain; charset=utf-8"
    if artifact.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"


def _resolve_repo_root() -> Path | None:
    current = Path.cwd()
    while True:
        if (current / _REPO_SENTINEL).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _resolve_diagnose_root() -> Path | None:
    if settings.DASHBOARD_COGAMES_DIAGNOSE_ROOT:
        return Path(settings.DASHBOARD_COGAMES_DIAGNOSE_ROOT)
    repo_root = _resolve_repo_root()
    if repo_root is None:
        return None
    return repo_root / "outputs" / "cogames-diagnose"


def _list_run_ids(diagnose_root: Path) -> list[str]:
    if not diagnose_root.is_dir():
        return []
    runs: list[str] = []
    for entry in diagnose_root.iterdir():
        if not entry.is_dir():
            continue
        if not _RUN_ID_RE.fullmatch(entry.name):
            continue
        runs.append(entry.name)
    runs.sort(reverse=True)
    return runs


def _read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_manifest(diagnose_root: Path, run_id: str) -> dict[str, Any] | None:
    manifest_path = diagnose_root / run_id / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = _read_json_file(manifest_path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _required_run_dir(diagnose_root: Path, run_id: str) -> Path:
    run_dir = diagnose_root / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Diagnose run not found")
    return run_dir


def _required_json(path: Path, detail: str) -> dict[str, Any]:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=detail)
    try:
        payload = _read_json_file(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail=detail) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=404, detail=detail)
    return payload


def create_cogames_diagnose_router() -> APIRouter:
    router = APIRouter(prefix="/dashboard/v1/cogames-diagnose", tags=["dashboard"])

    @router.get("/runs")
    @timed_http_handler
    async def list_runs(user: SoftmaxUser) -> DiagnoseRunsResponse:
        del user
        diagnose_root = _resolve_diagnose_root()
        if diagnose_root is None:
            return DiagnoseRunsResponse(runs=[])
        run_summaries = [
            DiagnoseRunSummary(run_id=run_id, manifest=_load_manifest(diagnose_root, run_id))
            for run_id in _list_run_ids(diagnose_root)
        ]
        return DiagnoseRunsResponse(runs=run_summaries)

    @router.get("/runs/{run_id}/manifest")
    @timed_http_handler
    async def get_manifest(run_id: str, user: SoftmaxUser) -> dict[str, Any]:
        del user
        _assert_safe_name(run_id, "run id")
        diagnose_root = _resolve_diagnose_root()
        if diagnose_root is None:
            raise HTTPException(status_code=404, detail="Diagnose run not found")
        run_dir = _required_run_dir(diagnose_root, run_id)
        return _required_json(run_dir / "manifest.json", detail="Manifest not found")

    @router.get("/runs/{run_id}/doctor-note")
    @timed_http_handler
    async def get_doctor_note(run_id: str, user: SoftmaxUser) -> dict[str, Any]:
        del user
        _assert_safe_name(run_id, "run id")
        diagnose_root = _resolve_diagnose_root()
        if diagnose_root is None:
            raise HTTPException(status_code=404, detail="Diagnose run not found")
        run_dir = _required_run_dir(diagnose_root, run_id)
        return _required_json(run_dir / "doctor_note.json", detail="Doctor note not found")

    @router.get("/runs/{run_id}/artifacts/{artifact}")
    @timed_http_handler
    async def get_artifact(run_id: str, artifact: str, user: SoftmaxUser) -> FileResponse:
        del user
        _assert_safe_name(run_id, "run id")
        _assert_safe_name(artifact, "artifact")
        diagnose_root = _resolve_diagnose_root()
        if diagnose_root is None:
            raise HTTPException(status_code=404, detail="Diagnose run not found")

        run_dir = _required_run_dir(diagnose_root, run_id)
        manifest = _load_manifest(diagnose_root, run_id)
        allowed = set()
        if isinstance(manifest, dict):
            artifact_files = manifest.get("artifact_files")
            if isinstance(artifact_files, list):
                allowed.update([item for item in artifact_files if isinstance(item, str)])
        allowed.add("manifest.json")
        allowed.add("doctor_note.json")

        if artifact not in allowed:
            raise HTTPException(status_code=404, detail="Artifact not found")

        artifact_path = run_dir / artifact
        if not artifact_path.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found")

        headers = {"Content-Disposition": f'attachment; filename="{artifact}"'} if artifact.endswith(".zip") else None
        return FileResponse(path=artifact_path, media_type=_content_type_for_artifact(artifact), headers=headers)

    return router
