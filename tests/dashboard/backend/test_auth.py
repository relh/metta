from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dashboard.backend.dashboard_backend import auth as dashboard_auth


def test_validate_token_via_login_service_service_account_success(monkeypatch) -> None:
    async def fake_get_service_account_user(token: str):
        assert token.startswith("ssa_")
        return SimpleNamespace(
            id="svc-user-1",
            email="admin+svc-user-1@serviceaccounts.softmax.com",
            is_softmax_team_member=True,
        )

    monkeypatch.setattr(dashboard_auth, "get_service_account_user", fake_get_service_account_user)

    user = asyncio.run(dashboard_auth.validate_token_via_login_service("ssa_mock_token_payload"))

    assert user is not None
    assert user.id == "svc-user-1"
    assert user.is_softmax_team_member is True
    assert user.is_service_account_user is True


def test_validate_token_via_login_service_service_account_lookup_error_returns_none(monkeypatch) -> None:
    async def fake_get_service_account_user(_token: str):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(dashboard_auth, "get_service_account_user", fake_get_service_account_user)

    user = asyncio.run(dashboard_auth.validate_token_via_login_service("ssa_mock_token_payload"))

    assert user is None
