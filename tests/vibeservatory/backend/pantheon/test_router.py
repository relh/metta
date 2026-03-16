from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibeservatory.backend.dashboard_backend.config import settings
from vibeservatory.backend.dashboard_backend.pantheon.router import create_pantheon_router


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pantheon_router_returns_seeded_stories_when_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_PANTHEON_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(create_pantheon_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/pantheon/v1/stories")
    assert response.status_code == 200
    payload = response.json()

    assert payload["source_root"] == str(tmp_path)
    assert len(payload["stories"]) == 3
    assert {story["hall"] for story in payload["stories"]} == {"fame", "same", "lame"}
    assert all(story["source"] == "seeded" for story in payload["stories"])


def test_pantheon_router_prefers_filesystem_stories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir(parents=True)
    _write_json(
        stories_dir / "batch.json",
        [
            {
                "story_id": "fs-fame",
                "hall": "fame",
                "title": "Filesystem Fame",
                "motif": "Extracted motif from replay cluster.",
                "summary": "A unique success behavior discovered in replay mining.",
                "policy": "policy-a:v1",
                "run_id": "run-a",
                "episode_id": "episode-1",
                "created_at": "2026-03-03T10:00:00Z",
                "tags": ["rare", "success"],
            },
            {
                "story_id": "fs-lame",
                "hall": "lame",
                "title": "Filesystem Lame",
                "motif": "Recurring failure loop motif.",
                "summary": "A repeated bad pattern discovered in replay mining.",
                "policy": "policy-b:v2",
                "run_id": "run-b",
                "episode_id": "episode-2",
                "created_at": "2026-03-02T10:00:00Z",
                "tags": ["failure", "loop"],
            },
        ],
    )
    monkeypatch.setattr(settings, "DASHBOARD_PANTHEON_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(create_pantheon_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/pantheon/v1/stories")
    assert response.status_code == 200
    payload = response.json()

    assert payload["source_root"] == str(tmp_path)
    assert [story["story_id"] for story in payload["stories"]] == ["fs-fame", "fs-lame"]
    assert all(story["source"] == "filesystem" for story in payload["stories"])


def test_pantheon_router_skips_invalid_files_and_stories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir(parents=True)
    _write_json(
        stories_dir / "good.json",
        [
            {
                "story_id": "fs-good",
                "hall": "fame",
                "title": "Filesystem Good",
                "motif": "A valid extracted motif.",
                "summary": "A valid filesystem story should still be returned.",
                "policy": "policy-good:v1",
                "run_id": "run-good",
                "episode_id": "episode-good",
                "created_at": "2026-03-04T10:00:00Z",
                "tags": ["valid"],
            },
            {
                "story_id": "fs-invalid-hall",
                "hall": "legend",
                "title": "Invalid Hall",
                "motif": "This should be skipped.",
                "summary": "Invalid hall should not fail the full endpoint.",
                "policy": "policy-invalid:v1",
                "created_at": "2026-03-04T09:00:00Z",
            },
        ],
    )
    (stories_dir / "bad.json").write_text("{ definitely-not-json", encoding="utf-8")
    monkeypatch.setattr(settings, "DASHBOARD_PANTHEON_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(create_pantheon_router())
    client = TestClient(app, base_url="http://localhost")

    response = client.get("/pantheon/v1/stories")
    assert response.status_code == 200
    payload = response.json()

    assert payload["source_root"] == str(tmp_path)
    assert [story["story_id"] for story in payload["stories"]] == ["fs-good"]
    assert payload["stories"][0]["source"] == "filesystem"


def test_pantheon_router_requires_softmax_auth_when_dev_bypass_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DASHBOARD_PANTHEON_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "DASHBOARD_DEV_AUTH_BYPASS", False)

    app = FastAPI()
    app.include_router(create_pantheon_router())
    client = TestClient(app, base_url="http://dashboard.example.com")

    response = client.get("/pantheon/v1/stories")
    assert response.status_code == 401
    assert response.json()["detail"] == "Failed to authenticate"
