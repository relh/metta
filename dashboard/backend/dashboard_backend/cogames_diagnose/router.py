import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from dashboard.backend.dashboard_backend.auth import SoftmaxUser
from dashboard.backend.dashboard_backend.config import settings
from metta.app_backend.route_logger import timed_http_handler

_RUN_ID_RE = re.compile(r"^(?!.*\.\.)[0-9A-Za-z._-]+$")
_ARTIFACT_COMPONENT_RE = re.compile(r"^[0-9A-Za-z._@+=-]+$")
_REPO_SENTINEL = "pnpm-workspace.yaml"


class DiagnoseRunSummary(BaseModel):
    run_id: str
    manifest: dict[str, Any] | None


class DiagnoseRunsResponse(BaseModel):
    runs: list[DiagnoseRunSummary]


def list_run_summaries() -> list[DiagnoseRunSummary]:
    diagnose_root = _resolve_diagnose_root()
    if diagnose_root is None:
        return []
    return [
        DiagnoseRunSummary(run_id=run_id, manifest=_load_manifest(diagnose_root, run_id))
        for run_id in _list_run_ids(diagnose_root)
    ]


def _assert_safe_name(value: str, field_name: str) -> None:
    if not _RUN_ID_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: {value}")


def _assert_safe_artifact_path(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"Invalid artifact: {value}")
    path = PurePosixPath(normalized)
    if path.is_absolute():
        raise HTTPException(status_code=422, detail=f"Invalid artifact: {value}")
    normalized_parts = path.parts
    if not normalized_parts:
        raise HTTPException(status_code=422, detail=f"Invalid artifact: {value}")
    for part in normalized_parts:
        if part in {".", ".."}:
            raise HTTPException(status_code=422, detail=f"Invalid artifact: {value}")
        if not _ARTIFACT_COMPONENT_RE.fullmatch(part):
            raise HTTPException(status_code=422, detail=f"Invalid artifact: {value}")
    return PurePosixPath(*normalized_parts).as_posix()


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


def _required_manifest_artifact_files(manifest: dict[str, Any]) -> set[str]:
    artifact_files = manifest.get("artifact_files")
    if not isinstance(artifact_files, list):
        raise HTTPException(status_code=422, detail="Manifest missing artifact_files")
    if not all(isinstance(item, str) for item in artifact_files):
        raise HTTPException(status_code=422, detail="Manifest artifact_files must be a list of strings")
    return set(artifact_files)


def create_cogames_diagnose_router() -> APIRouter:
    router = APIRouter(prefix="/dashboard/v1/cogames-diagnose", tags=["dashboard"])

    @router.get("/runs")
    @timed_http_handler
    async def list_runs(user: SoftmaxUser) -> DiagnoseRunsResponse:
        del user
        return DiagnoseRunsResponse(runs=list_run_summaries())

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

    @router.get("/runs/{run_id}/artifacts/{artifact_path:path}")
    @timed_http_handler
    async def get_artifact(run_id: str, artifact_path: str, user: SoftmaxUser) -> FileResponse:
        del user
        _assert_safe_name(run_id, "run id")
        artifact = _assert_safe_artifact_path(artifact_path)
        diagnose_root = _resolve_diagnose_root()
        if diagnose_root is None:
            raise HTTPException(status_code=404, detail="Diagnose run not found")

        run_dir = _required_run_dir(diagnose_root, run_id)
        manifest = _required_json(run_dir / "manifest.json", detail="Manifest not found")
        allowed = _required_manifest_artifact_files(manifest)
        allowed.add("manifest.json")
        allowed.add("doctor_note.json")

        if artifact not in allowed:
            raise HTTPException(status_code=404, detail="Artifact not found")

        artifact_file = run_dir / Path(artifact)
        if not artifact_file.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found")
        if not artifact_file.resolve().is_relative_to(run_dir.resolve()):
            raise HTTPException(status_code=404, detail="Artifact not found")

        headers = {"Content-Disposition": f'attachment; filename="{artifact}"'} if artifact.endswith(".zip") else None
        return FileResponse(path=artifact_file, media_type=_content_type_for_artifact(artifact), headers=headers)

    return router
