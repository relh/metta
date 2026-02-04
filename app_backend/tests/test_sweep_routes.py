"""Tests for sweep coordination routes."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from metta.app_backend.auth import User
from metta.app_backend.models.sweep import Sweep
from metta.app_backend.server import create_app


@pytest.fixture
def test_client():
    """Create a test client."""
    app = create_app()
    return TestClient(app)


def _make_sweep(sweep_id: uuid.UUID, name: str = "test_sweep", run_counter: int = 0) -> Sweep:
    """Helper to create a Sweep model instance."""
    return Sweep(
        id=sweep_id,
        name=name,
        project="test_project",
        entity="test_entity",
        wandb_sweep_id="wandb_123",
        state="running",
        run_counter=run_counter,
        user_id="test@example.com",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_create_sweep_creates_new(test_client: TestClient, auth_headers: dict[str, str]):
    """Test creating a new sweep."""
    test_sweep_id = uuid.uuid4()

    with (
        patch("metta.app_backend.queries.sweep_queries.get_sweep_by_name", new_callable=AsyncMock) as mock_get,
        patch("metta.app_backend.queries.sweep_queries.create_sweep", new_callable=AsyncMock) as mock_create,
    ):
        mock_get.return_value = None
        mock_create.return_value = test_sweep_id

        response = test_client.post(
            "/sweeps/test_sweep/create_sweep",
            json={
                "project": "test_project",
                "entity": "test_entity",
                "wandb_sweep_id": "wandb_123",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == {"created": True, "sweep_id": str(test_sweep_id)}

        mock_get.assert_called_once_with("test_sweep")
        mock_create.assert_called_once_with(
            name="test_sweep",
            project="test_project",
            entity="test_entity",
            wandb_sweep_id="wandb_123",
            user_id="debug_user_id",
        )


def test_create_sweep_returns_existing(test_client: TestClient, auth_headers: dict[str, str]):
    """Test returning existing sweep info (idempotent)."""
    existing_sweep_id = uuid.uuid4()
    existing_sweep = _make_sweep(existing_sweep_id)

    with (
        patch("metta.app_backend.queries.sweep_queries.get_sweep_by_name", new_callable=AsyncMock) as mock_get,
        patch("metta.app_backend.queries.sweep_queries.create_sweep", new_callable=AsyncMock) as mock_create,
    ):
        mock_get.return_value = existing_sweep

        response = test_client.post(
            "/sweeps/test_sweep/create_sweep",
            json={
                "project": "test_project",
                "entity": "test_entity",
                "wandb_sweep_id": "wandb_123",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == {"created": False, "sweep_id": str(existing_sweep_id)}

        mock_get.assert_called_once_with("test_sweep")
        mock_create.assert_not_called()


def test_create_sweep_with_machine_token(test_client: TestClient):
    """Test creating sweep with machine token authentication."""
    test_sweep_id = uuid.uuid4()

    mock_validate = AsyncMock(
        return_value=User(id="machine_user_id", email="machine_user@example.com", is_softmax_team_member=True)
    )

    with (
        patch("metta.app_backend.queries.sweep_queries.get_sweep_by_name", new_callable=AsyncMock) as mock_get,
        patch("metta.app_backend.queries.sweep_queries.create_sweep", new_callable=AsyncMock) as mock_create,
        patch("metta.app_backend.auth.validate_token_via_login_service", mock_validate),
    ):
        mock_get.return_value = None
        mock_create.return_value = test_sweep_id

        response = test_client.post(
            "/sweeps/test_sweep/create_sweep",
            json={
                "project": "test_project",
                "entity": "test_entity",
                "wandb_sweep_id": "wandb_123",
            },
            headers={"X-Auth-Token": "machine_token_123"},
        )

        assert response.status_code == 200
        assert response.json() == {"created": True, "sweep_id": str(test_sweep_id)}

        mock_validate.assert_called_once_with("machine_token_123")

        mock_create.assert_called_once_with(
            name="test_sweep",
            project="test_project",
            entity="test_entity",
            wandb_sweep_id="wandb_123",
            user_id="machine_user_id",
        )


def test_get_sweep_exists(test_client: TestClient, auth_headers: dict[str, str]):
    """Test getting an existing sweep."""
    sweep_id = uuid.uuid4()
    sweep = _make_sweep(sweep_id)

    with patch("metta.app_backend.queries.sweep_queries.get_sweep_by_name", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = sweep

        response = test_client.get("/sweeps/test_sweep", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["wandb_sweep_id"] == "wandb_123"


def test_get_sweep_not_exists(test_client: TestClient, auth_headers: dict[str, str]):
    """Test getting a non-existent sweep."""
    with patch("metta.app_backend.queries.sweep_queries.get_sweep_by_name", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        response = test_client.get("/sweeps/nonexistent", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["wandb_sweep_id"] == ""


def test_get_next_run_id(test_client: TestClient, auth_headers: dict[str, str]):
    """Test getting the next run ID (atomic counter)."""
    sweep_id = uuid.uuid4()
    sweep = _make_sweep(sweep_id, run_counter=41)

    with (
        patch("metta.app_backend.queries.sweep_queries.get_sweep_by_name", new_callable=AsyncMock) as mock_get,
        patch(
            "metta.app_backend.queries.sweep_queries.get_next_sweep_run_counter", new_callable=AsyncMock
        ) as mock_next,
    ):
        mock_get.return_value = sweep
        mock_next.return_value = 42

        response = test_client.post("/sweeps/test_sweep/runs/next", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "test_sweep.r.42"

        mock_get.assert_called_once_with("test_sweep")
        mock_next.assert_called_once_with(sweep_id)


def test_get_next_run_id_sweep_not_found(test_client: TestClient, auth_headers: dict[str, str]):
    """Test getting next run ID for non-existent sweep."""
    with patch("metta.app_backend.queries.sweep_queries.get_sweep_by_name", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        response = test_client.post("/sweeps/nonexistent/runs/next", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
