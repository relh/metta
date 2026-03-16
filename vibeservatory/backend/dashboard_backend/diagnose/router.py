import json
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from metta.app_backend.route_logger import timed_http_handler
from vibeservatory.backend.dashboard_backend.auth import SoftmaxUser
from vibeservatory.backend.dashboard_backend.config import settings

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
    return repo_root / "outputs" / "cogames-diagnose" if (repo_root := _resolve_repo_root()) is not None else None


def _required_diagnose_root() -> Path:
    diagnose_root = _resolve_diagnose_root()
    if diagnose_root is None:
        raise HTTPException(status_code=500, detail="Diagnose root is not configured")
    diagnose_root.mkdir(parents=True, exist_ok=True)
    return diagnose_root


def _list_run_ids(diagnose_root: Path) -> list[str]:
    if not diagnose_root.is_dir():
        return []
    return sorted(
        (entry.name for entry in diagnose_root.iterdir() if entry.is_dir() and _RUN_ID_RE.fullmatch(entry.name)),
        reverse=True,
    )


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


def _required_diagnose_run_dir(run_id: str) -> Path:
    diagnose_root = _resolve_diagnose_root()
    if diagnose_root is None:
        raise HTTPException(status_code=404, detail="Diagnose run not found")
    return _required_run_dir(diagnose_root, run_id)


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


def _assert_safe_bundle_member(value: str) -> PurePosixPath:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"Invalid bundle entry: {value}")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts:
        raise HTTPException(status_code=422, detail=f"Invalid bundle entry: {value}")
    for part in path.parts:
        if part in {".", ".."}:
            raise HTTPException(status_code=422, detail=f"Invalid bundle entry: {value}")
        if not _ARTIFACT_COMPONENT_RE.fullmatch(part):
            raise HTTPException(status_code=422, detail=f"Invalid bundle entry: {value}")
    return PurePosixPath(*path.parts)


def _read_bundle_json(bundle: zipfile.ZipFile, entry: zipfile.ZipInfo, *, detail: str) -> dict[str, Any]:
    try:
        payload = json.loads(bundle.read(entry).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=detail) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail=detail)
    return payload


def _resolve_bundle_members(bundle: zipfile.ZipFile) -> tuple[str, dict[str, zipfile.ZipInfo], dict[str, Any]]:
    files_by_path: dict[PurePosixPath, zipfile.ZipInfo] = {}
    for member in bundle.infolist():
        if member.is_dir():
            continue
        safe_path = _assert_safe_bundle_member(member.filename)
        files_by_path[safe_path] = member
    if not files_by_path:
        raise HTTPException(status_code=422, detail="Bundle contains no files")

    manifest_paths = [path for path in files_by_path if path.name == "manifest.json"]
    if len(manifest_paths) != 1:
        raise HTTPException(status_code=422, detail="Bundle must include exactly one manifest.json")
    bundle_root = manifest_paths[0].parent

    relative_members: dict[str, zipfile.ZipInfo] = {}
    for path, member in files_by_path.items():
        if not path.is_relative_to(bundle_root):
            continue
        relative = path.relative_to(bundle_root).as_posix()
        normalized_relative = _assert_safe_artifact_path(relative)
        relative_members[normalized_relative] = member

    if "doctor_note.json" not in relative_members:
        raise HTTPException(status_code=422, detail="Bundle missing doctor_note.json")
    if "manifest.json" not in relative_members:
        raise HTTPException(status_code=422, detail="Bundle missing manifest.json")

    manifest_payload = _read_bundle_json(bundle, relative_members["manifest.json"], detail="Invalid manifest.json")
    run_id_raw = manifest_payload.get("run_id")
    if not isinstance(run_id_raw, str) or not run_id_raw.strip():
        raise HTTPException(status_code=422, detail="Manifest missing run_id")
    run_id = run_id_raw.strip()
    _assert_safe_name(run_id, "run id")
    return run_id, relative_members, manifest_payload


def _replace_run_directory(*, run_dir: Path, staged_run_dir: Path) -> None:
    backup_dir: Path | None = None
    try:
        if run_dir.exists():
            backup_dir = run_dir.with_name(f".{run_dir.name}.backup-{uuid.uuid4().hex}")
            run_dir.replace(backup_dir)
        staged_run_dir.replace(run_dir)
    except OSError:
        if backup_dir is not None and backup_dir.exists() and not run_dir.exists():
            backup_dir.replace(run_dir)
        raise
    else:
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir)


def _import_bundle(upload: UploadFile) -> DiagnoseRunSummary:
    upload_name = upload.filename.strip() if upload.filename is not None else ""
    if upload_name and not upload_name.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Uploaded file must be a .zip bundle")

    staged_run_dir: Path | None = None
    try:
        upload.file.seek(0)
        with zipfile.ZipFile(upload.file) as bundle:
            run_id, relative_members, manifest_payload = _resolve_bundle_members(bundle)
            _required_manifest_artifact_files(manifest_payload)

            diagnose_root = _required_diagnose_root()
            run_dir = diagnose_root / run_id
            staged_run_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.import-", dir=diagnose_root))
            staged_run_dir_resolved = staged_run_dir.resolve()

            for relative_path, member in relative_members.items():
                target_path = staged_run_dir / Path(relative_path)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if not target_path.resolve().is_relative_to(staged_run_dir_resolved):
                    raise HTTPException(status_code=422, detail=f"Invalid bundle entry: {relative_path}")
                with bundle.open(member, "r") as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)

            _replace_run_directory(run_dir=run_dir, staged_run_dir=staged_run_dir)
            staged_run_dir = None

    except HTTPException:
        raise
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=422, detail="Uploaded file is not a valid zip bundle") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to import bundle: {exc}") from exc
    finally:
        if staged_run_dir is not None and staged_run_dir.exists():
            shutil.rmtree(staged_run_dir, ignore_errors=True)

    return DiagnoseRunSummary(run_id=run_id, manifest=manifest_payload)


def create_diagnose_router() -> APIRouter:
    router = APIRouter(prefix="/diagnose/v1", tags=["diagnose"])

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
        run_dir = _required_diagnose_run_dir(run_id)
        return _required_json(run_dir / "manifest.json", detail="Manifest not found")

    @router.get("/runs/{run_id}/doctor-note")
    @timed_http_handler
    async def get_doctor_note(run_id: str, user: SoftmaxUser) -> dict[str, Any]:
        del user
        _assert_safe_name(run_id, "run id")
        run_dir = _required_diagnose_run_dir(run_id)
        return _required_json(run_dir / "doctor_note.json", detail="Doctor note not found")

    @router.get("/runs/{run_id}/artifacts/{artifact_path:path}")
    @timed_http_handler
    async def get_artifact(run_id: str, artifact_path: str, user: SoftmaxUser) -> FileResponse:
        del user
        _assert_safe_name(run_id, "run id")
        artifact = _assert_safe_artifact_path(artifact_path)
        run_dir = _required_diagnose_run_dir(run_id)
        manifest = _required_json(run_dir / "manifest.json", detail="Manifest not found")
        allowed = _required_manifest_artifact_files(manifest) | {"manifest.json", "doctor_note.json"}

        if artifact not in allowed:
            raise HTTPException(status_code=404, detail="Artifact not found")

        artifact_file = run_dir / Path(artifact)
        if not artifact_file.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found")
        if not artifact_file.resolve().is_relative_to(run_dir.resolve()):
            raise HTTPException(status_code=404, detail="Artifact not found")

        headers = {"Content-Disposition": f'attachment; filename="{artifact}"'} if artifact.endswith(".zip") else None
        return FileResponse(path=artifact_file, media_type=_content_type_for_artifact(artifact), headers=headers)

    @router.post("/runs/upload")
    @timed_http_handler
    async def upload_run_bundle(user: SoftmaxUser, bundle: Annotated[UploadFile, File(...)]) -> DiagnoseRunSummary:
        del user
        return _import_bundle(bundle)

    return router
