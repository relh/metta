from unittest.mock import AsyncMock, patch

import httpx
import pytest

from metta.app_backend.auth import User
from metta.app_backend.user_data import Ownable, UserRow, _user_info_cache, fill_user_data


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the module-level user info cache between tests."""
    _user_info_cache.clear()


RESOLVE_USERS = {
    "u1": {"id": "u1", "name": "Alice", "email": "alice@softmax.com", "isSoftmaxTeamMember": True},
    "u2": {"id": "u2", "name": "Bob", "email": "bob@example.com", "isSoftmaxTeamMember": False},
}

SOFTMAX_USER = User(id="u1", email="admin@softmax.com", is_softmax_team_member=True)
REGULAR_USER = User(id="u2", email="user@example.com", is_softmax_team_member=False)


@pytest.fixture
def mock_http():
    """Patch httpx.AsyncClient and yield the mock client instance."""
    with patch("metta.app_backend.user_data.httpx.AsyncClient") as MockClient:
        client = AsyncMock()
        client.post.return_value = httpx.Response(200, json={"users": RESOLVE_USERS})
        MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        yield client


@pytest.mark.asyncio
async def test_softmax_user_sees_sensitive_fields(mock_http):
    entities = [Ownable(user_id="u1"), Ownable(user_id="u2")]
    await fill_user_data(entities, current_user=SOFTMAX_USER)

    assert entities[0].user == UserRow(id="u1", name="Alice", email="alice@softmax.com", is_softmax_team_member=True)
    assert entities[1].user == UserRow(id="u2", name="Bob", email="bob@example.com", is_softmax_team_member=False)


@pytest.mark.asyncio
async def test_regular_user_hides_sensitive_fields(mock_http):
    entities = [Ownable(user_id="u1")]
    await fill_user_data(entities, current_user=REGULAR_USER)

    assert entities[0].user is not None
    assert entities[0].user.name == "Alice"
    assert entities[0].user.email is None
    assert entities[0].user.is_softmax_team_member is None


@pytest.mark.asyncio
async def test_no_current_user_hides_sensitive_fields(mock_http):
    entities = [Ownable(user_id="u1")]
    await fill_user_data(entities, current_user=None)

    assert entities[0].user is not None
    assert entities[0].user.name == "Alice"
    assert entities[0].user.email is None
    assert entities[0].user.is_softmax_team_member is None


@pytest.mark.asyncio
async def test_empty_entities():
    """No HTTP call when entity list is empty."""
    with patch("metta.app_backend.user_data.httpx.AsyncClient") as MockClient:
        await fill_user_data([])
        MockClient.assert_not_called()


@pytest.mark.asyncio
async def test_no_auth_secret():
    """No HTTP call when OBSERVATORY_AUTH_SECRET is unset."""
    entities = [Ownable(user_id="u1")]
    with (
        patch("metta.app_backend.user_data.settings") as mock_settings,
        patch("metta.app_backend.user_data.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.OBSERVATORY_AUTH_SECRET = None
        mock_settings.LOGIN_SERVICE_URL = "https://softmax.com"
        await fill_user_data(entities)
        MockClient.assert_not_called()
    assert entities[0].user is None


@pytest.mark.asyncio
async def test_non_200_response(mock_http):
    """Non-200 response leaves user as None."""
    mock_http.post.return_value = httpx.Response(500, json={})
    entities = [Ownable(user_id="u1")]
    await fill_user_data(entities, current_user=SOFTMAX_USER)
    assert entities[0].user is None


@pytest.mark.asyncio
async def test_http_exception(mock_http):
    """HTTP exception is caught; user stays None."""
    mock_http.post.side_effect = httpx.ConnectError("connection refused")
    entities = [Ownable(user_id="u1")]
    await fill_user_data(entities, current_user=SOFTMAX_USER)
    assert entities[0].user is None


@pytest.mark.asyncio
async def test_deduplicates_user_ids(mock_http):
    """Duplicate user_ids are sent as unique set."""
    entities = [Ownable(user_id="u1"), Ownable(user_id="u1"), Ownable(user_id="u1")]
    await fill_user_data(entities, current_user=SOFTMAX_USER)

    sent_ids = mock_http.post.call_args.kwargs.get("json", mock_http.post.call_args[1].get("json", {}))["userIds"]
    assert sent_ids == ["u1"]
    assert all(e.user is not None and e.user.name == "Alice" for e in entities)


@pytest.mark.asyncio
async def test_unknown_user_id(mock_http):
    """User not in resolve response stays None."""
    entities = [Ownable(user_id="unknown-id")]
    await fill_user_data(entities, current_user=SOFTMAX_USER)
    assert entities[0].user is None


@pytest.mark.asyncio
async def test_sends_correct_request(mock_http):
    """Verify correct URL, headers, and payload."""
    entities = [Ownable(user_id="u1")]
    with patch("metta.app_backend.user_data.settings") as mock_settings:
        mock_settings.OBSERVATORY_AUTH_SECRET = "my-secret"
        mock_settings.LOGIN_SERVICE_URL = "https://softmax.com"
        await fill_user_data(entities, current_user=SOFTMAX_USER)

    mock_http.post.assert_called_once_with(
        "https://softmax.com/api/users/resolve",
        json={"userIds": ["u1"]},
        headers={"X-Auth-Secret": "my-secret"},
        timeout=5.0,
    )
