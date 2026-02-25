from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from metta.app_backend.routes.tournament_routes import _list_available_episode_runner_compat_versions


@pytest.mark.asyncio
async def test_list_available_compat_versions_registry_failure_returns_503() -> None:
    with patch("metta.app_backend.routes.tournament_routes.httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("connection refused")
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await _list_available_episode_runner_compat_versions()

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_list_available_compat_versions_handles_null_tags() -> None:
    token_response = MagicMock()
    token_response.raise_for_status = MagicMock(return_value=None)
    token_response.json.return_value = {"token": "test-token"}

    tags_response = MagicMock()
    tags_response.raise_for_status = MagicMock(return_value=None)
    tags_response.json.return_value = {"tags": None}
    tags_response.links = {}

    with patch("metta.app_backend.routes.tournament_routes.httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        client.get.side_effect = [token_response, tags_response]
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        compat_versions = await _list_available_episode_runner_compat_versions()

    assert compat_versions == []
