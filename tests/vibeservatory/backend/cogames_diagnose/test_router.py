from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibeservatory.backend.dashboard_backend.cogames_diagnose import router as diagnose_router
from vibeservatory.backend.dashboard_backend.cogames_diagnose.router import (
    create_cogames_diagnose_router,
)
from vibeservatory.backend.dashboard_backend.config import settings


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_bundle(bundle_path: Path, *, run_id: str, policy: str = "uploaded-policy") -> None:
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "portable_bundle/manifest.json",
            json.dumps(
                {
                    "run_id": run_id,
                    "created_at": "2026-03-01T00:00:00Z",
                    "command": "cogames diagnose class=random --bundle-zip ./diagnose_bundle.zip",
                    "policy": policy,
                    "pack_id": "pack",
                    "pack_version": "1",
                    "stage_status": "stage2_completed",
                    "run_status": "complete",
                    "artifact_files": ["diagnose_report.html", "replay_bundle.zip"],
                }
            ),
        )
        bundle.writestr(
            "portable_bundle/doctor_note.json",
            json.dumps(
                {
                    "run_id": run_id,
                    "status": "complete",
                    "stage_status": "stage2_completed",
                    "dominant_issue": "none",
                    "axes": [],
                    "stage1_probe_catalog": [],
                    "stage1_probe_evaluations": [],
                    "symptoms": [],
                    "prescriptions": [],
                    "notes": [],
                }
            ),
        )
        bundle.writestr("portable_bundle/diagnose_report.html", "<html>uploaded</html>")
        bundle.writestr("portable_bundle/replay_bundle.zip", "zip-bytes")


def test_cogames_diagnose_router_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = "run_123-abc.def"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)

    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "created_at": "2026-02-21T00:00:00Z",
            "command": "cogames diagnose some-policy",
            "policy": "some-policy",
            "pack_id": "pack",
            "pack_version": "1",
            "stage_status": "stage1",
            "run_status": "complete",
            "artifact_files": [
                "diagnose_report.html",
                "replays/episode_0.json.z",
                "replays/episode+meta.json.zst",
            ],
        },
    )
    _write_json(
        run_dir / "doctor_note.json",
        {
            "run_id": run_id,
            "status": "complete",
            "stage_status": "stage1",
            "dominant_issue": "none",
            "axes": [],
            "stage1_probe_catalog": [],
            "stage1_probe_evaluations": [],
            "symptoms": [],
            "prescriptions": [],
            "notes": [],
        },
    )
    (run_dir / "diagnose_report.html").write_text("<html>report</html>", encoding="utf-8")
    (run_dir / "replays").mkdir(parents=True, exist_ok=True)
    (run_dir / "replays" / "episode_0.json.z").write_text("{}", encoding="utf-8")
    (run_dir / "replays" / "episode+meta.json.zst").write_text("{}", encoding="utf-8")
    (run_dir / "not-allowlisted.txt").write_text("hidden", encoding="utf-8")

    monkeypatch.setattr(settings, "DASHBOARD_COGAMES_DIAGNOSE_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(create_cogames_diagnose_router())
    client = TestClient(app, base_url="http://localhost")

    runs_response = client.get("/dashboard/v1/cogames-diagnose/runs")
    assert runs_response.status_code == 200
    assert runs_response.json() == {
        "runs": [
            {
                "run_id": run_id,
                "manifest": {
                    "run_id": run_id,
                    "created_at": "2026-02-21T00:00:00Z",
                    "command": "cogames diagnose some-policy",
                    "policy": "some-policy",
                    "pack_id": "pack",
                    "pack_version": "1",
                    "stage_status": "stage1",
                    "run_status": "complete",
                    "artifact_files": [
                        "diagnose_report.html",
                        "replays/episode_0.json.z",
                        "replays/episode+meta.json.zst",
                    ],
                },
            }
        ]
    }

    manifest_response = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/manifest")
    assert manifest_response.status_code == 200
    assert manifest_response.json()["run_id"] == run_id

    doctor_note_response = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/doctor-note")
    assert doctor_note_response.status_code == 200
    assert doctor_note_response.json()["run_id"] == run_id

    artifact_response = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/artifacts/diagnose_report.html")
    assert artifact_response.status_code == 200
    assert artifact_response.text == "<html>report</html>"
    assert artifact_response.headers["content-type"] == "text/html; charset=utf-8"

    nested_artifact = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/artifacts/replays/episode_0.json.z")
    assert nested_artifact.status_code == 200
    assert nested_artifact.text == "{}"
    assert nested_artifact.headers["content-type"] == "application/octet-stream"

    nested_plus_artifact = client.get(
        f"/dashboard/v1/cogames-diagnose/runs/{run_id}/artifacts/replays/episode%2Bmeta.json.zst"
    )
    assert nested_plus_artifact.status_code == 200
    assert nested_plus_artifact.text == "{}"
    assert nested_plus_artifact.headers["content-type"] == "application/octet-stream"

    disallowed_artifact = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/artifacts/not-allowlisted.txt")
    assert disallowed_artifact.status_code == 404

    traversal_artifact = client.get(
        f"/dashboard/v1/cogames-diagnose/runs/{run_id}/artifacts/replays/%2E%2E/diagnose_report.html"
    )
    assert traversal_artifact.status_code == 422

    invalid_run_id = client.get("/dashboard/v1/cogames-diagnose/runs/%2E%2E/manifest")
    assert invalid_run_id.status_code == 422


def test_cogames_diagnose_router_rejects_manifest_without_artifact_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "invalid_manifest_run_001"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)

    # artifact_files is required for artifact allowlisting.
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "created_at": "2026-02-20T00:00:00Z",
            "command": "cogames diagnose some-policy",
            "policy": "some-policy",
            "pack_id": "pack",
            "pack_version": "1",
            "stage_status": "stage1_incomplete",
            "run_status": "incomplete",
        },
    )
    _write_json(
        run_dir / "doctor_note.json",
        {
            "run_id": run_id,
            "status": "incomplete",
            "stage_status": "stage1_incomplete",
            "dominant_issue": "stability",
            "axes": [],
            "stage1_probe_catalog": [],
            "stage1_probe_evaluations": [],
            "symptoms": [],
            "prescriptions": [],
            "notes": [],
        },
    )
    (run_dir / "diagnose_report.html").write_text("<html>report</html>", encoding="utf-8")

    monkeypatch.setattr(settings, "DASHBOARD_COGAMES_DIAGNOSE_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(create_cogames_diagnose_router())
    client = TestClient(app, base_url="http://localhost")

    manifest_response = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/manifest")
    assert manifest_response.status_code == 200
    assert manifest_response.json()["run_id"] == run_id

    artifact_response = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/artifacts/diagnose_report.html")
    assert artifact_response.status_code == 422
    assert artifact_response.json()["detail"] == "Manifest missing artifact_files"


def test_cogames_diagnose_router_upload_bundle_imports_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "uploaded_run_001"
    bundle_path = tmp_path / "diagnose_bundle.zip"
    _write_bundle(bundle_path, run_id=run_id, policy="uploaded-policy")

    monkeypatch.setattr(settings, "DASHBOARD_COGAMES_DIAGNOSE_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(create_cogames_diagnose_router())
    client = TestClient(app, base_url="http://localhost")

    with bundle_path.open("rb") as bundle_file:
        upload_response = client.post(
            "/dashboard/v1/cogames-diagnose/runs/upload",
            files={"bundle": (bundle_path.name, bundle_file, "application/zip")},
        )
    assert upload_response.status_code == 200
    assert upload_response.json()["run_id"] == run_id

    imported_manifest_path = tmp_path / run_id / "manifest.json"
    assert imported_manifest_path.is_file()
    assert json.loads(imported_manifest_path.read_text())["policy"] == "uploaded-policy"

    runs_response = client.get("/dashboard/v1/cogames-diagnose/runs")
    assert runs_response.status_code == 200
    assert runs_response.json()["runs"][0]["run_id"] == run_id

    doctor_note_response = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/doctor-note")
    assert doctor_note_response.status_code == 200
    assert doctor_note_response.json()["run_id"] == run_id


def test_cogames_diagnose_router_upload_bundle_keeps_existing_run_when_import_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "uploaded_run_002"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "created_at": "2026-03-01T00:00:00Z",
            "command": "cogames diagnose class=baseline",
            "policy": "existing-policy",
            "pack_id": "pack",
            "pack_version": "1",
            "stage_status": "stage2_completed",
            "run_status": "complete",
            "artifact_files": ["diagnose_report.html", "replay_bundle.zip"],
        },
    )
    _write_json(
        run_dir / "doctor_note.json",
        {
            "run_id": run_id,
            "status": "complete",
            "stage_status": "stage2_completed",
            "dominant_issue": "none",
            "axes": [],
            "stage1_probe_catalog": [],
            "stage1_probe_evaluations": [],
            "symptoms": [],
            "prescriptions": [],
            "notes": [],
        },
    )
    (run_dir / "diagnose_report.html").write_text("<html>existing</html>", encoding="utf-8")
    (run_dir / "replay_bundle.zip").write_text("existing-zip-bytes", encoding="utf-8")

    bundle_path = tmp_path / "replacement_bundle.zip"
    _write_bundle(bundle_path, run_id=run_id, policy="replacement-policy")

    monkeypatch.setattr(settings, "DASHBOARD_COGAMES_DIAGNOSE_ROOT", str(tmp_path))

    copy_count = 0
    original_copyfileobj = diagnose_router.shutil.copyfileobj

    def _failing_copyfileobj(src: Any, dst: Any, length: int = 0) -> None:
        nonlocal copy_count
        copy_count += 1
        if copy_count == 2:
            raise OSError("simulated disk full")
        original_copyfileobj(src, dst, length)

    monkeypatch.setattr(diagnose_router.shutil, "copyfileobj", _failing_copyfileobj)

    app = FastAPI()
    app.include_router(create_cogames_diagnose_router())
    client = TestClient(app, base_url="http://localhost")

    with bundle_path.open("rb") as bundle_file:
        upload_response = client.post(
            "/dashboard/v1/cogames-diagnose/runs/upload",
            files={"bundle": (bundle_path.name, bundle_file, "application/zip")},
        )

    assert upload_response.status_code == 500
    assert "Failed to import bundle" in upload_response.json()["detail"]
    assert json.loads((run_dir / "manifest.json").read_text())["policy"] == "existing-policy"
    assert (run_dir / "diagnose_report.html").read_text(encoding="utf-8") == "<html>existing</html>"
    assert (run_dir / "replay_bundle.zip").read_text(encoding="utf-8") == "existing-zip-bytes"


def test_cogames_diagnose_router_upload_bundle_streams_large_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "uploaded_run_003"
    bundle_path = tmp_path / "streaming_bundle.zip"
    _write_bundle(bundle_path, run_id=run_id, policy="streaming-policy")

    original_read = zipfile.ZipFile.read

    def _guarded_read(self: zipfile.ZipFile, name: str | zipfile.ZipInfo, pwd: bytes | None = None) -> bytes:
        member_name = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
        if member_name.endswith("replay_bundle.zip"):
            raise AssertionError("bundle.read should not be used for large artifact extraction")
        return original_read(self, name, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "read", _guarded_read)
    monkeypatch.setattr(settings, "DASHBOARD_COGAMES_DIAGNOSE_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(create_cogames_diagnose_router())
    client = TestClient(app, base_url="http://localhost")

    with bundle_path.open("rb") as bundle_file:
        upload_response = client.post(
            "/dashboard/v1/cogames-diagnose/runs/upload",
            files={"bundle": (bundle_path.name, bundle_file, "application/zip")},
        )

    assert upload_response.status_code == 200
    assert upload_response.json()["run_id"] == run_id
    assert (tmp_path / run_id / "replay_bundle.zip").read_text(encoding="utf-8") == "zip-bytes"
