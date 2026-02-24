from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.dashboard_backend.cogames_diagnose.router import (
    create_cogames_diagnose_router,
)
from dashboard.backend.dashboard_backend.config import settings


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


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
