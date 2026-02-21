from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from dashboard.backend.dashboard_backend.cogames_diagnose.router import (
    _assert_safe_name,
    create_cogames_diagnose_router,
)
from dashboard.backend.dashboard_backend.config import settings


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_assert_safe_name_rejects_dot_dot_sequences() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _assert_safe_name("..", "run id")
    assert exc_info.value.status_code == 422

    with pytest.raises(HTTPException) as exc_info:
        _assert_safe_name("run..id", "run id")
    assert exc_info.value.status_code == 422


def test_assert_safe_name_allows_legit_names() -> None:
    _assert_safe_name("run_123-abc.def", "run id")


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
            "artifact_files": ["diagnose_report.html"],
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
                    "artifact_files": ["diagnose_report.html"],
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

    disallowed_artifact = client.get(f"/dashboard/v1/cogames-diagnose/runs/{run_id}/artifacts/not-allowlisted.txt")
    assert disallowed_artifact.status_code == 404

    invalid_run_id = client.get("/dashboard/v1/cogames-diagnose/runs/%2E%2E/manifest")
    assert invalid_run_id.status_code == 422
