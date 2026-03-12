from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from metta.app_backend.database import db_session
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.user_settings import UserSettings
from metta.app_backend.test_support.client_adapter import get_fake_softmax_user
from metta.app_backend.user_data import UserRow


@pytest.mark.asyncio
async def test_admin_routes_require_admin_flag(test_client, softmax_headers: dict[str, str]) -> None:
    response = test_client.get("/admin/users", headers=softmax_headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "User is not a softmax admin"}


@pytest.mark.asyncio
async def test_admin_routes_allow_admin_flag(test_client, softmax_headers: dict[str, str]) -> None:
    async with db_session() as session:
        session.add(UserSettings(user_id=get_fake_softmax_user().id, admin=True))
        alice_policy = Policy(
            name="alice-policy",
            user_id="u1",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        session.add(alice_policy)
        await session.flush()
        session.add(
            PolicyVersion(
                policy_id=alice_policy.id,
                version=1,
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            )
        )
        session.add(
            PolicyVersion(
                policy_id=alice_policy.id,
                version=2,
                created_at=datetime(2026, 3, 5, 18, 30, tzinfo=UTC),
            )
        )

    with patch(
        "metta.app_backend.routes.admin_routes.load_all_users",
        AsyncMock(
            return_value=[
                UserRow(id="u2", name="Bob", email="bob@example.com"),
                UserRow(id="u1", name="Alice", email="alice@softmax.com"),
            ]
        ),
    ):
        response = test_client.get("/admin/users", headers=softmax_headers)

    assert response.status_code == 200
    assert response.json() == {
        "users": [
            {
                "id": "u1",
                "name": "Alice",
                "email": "alice@softmax.com",
                "is_softmax_team_member": None,
                "discord_id": None,
                "first_policy_upload_at": "2026-03-01T12:00:00",
                "last_policy_upload_at": "2026-03-05T18:30:00",
            },
            {
                "id": "u2",
                "name": "Bob",
                "email": "bob@example.com",
                "is_softmax_team_member": None,
                "discord_id": None,
                "first_policy_upload_at": None,
                "last_policy_upload_at": None,
            },
        ]
    }


@pytest.mark.asyncio
async def test_whoami_exposes_admin_flag(test_client, softmax_headers: dict[str, str]) -> None:
    async with db_session() as session:
        session.add(UserSettings(user_id=get_fake_softmax_user().id, admin=True))

    response = test_client.get("/whoami", headers=softmax_headers)

    assert response.status_code == 200
    assert response.json() == {
        "user_email": "softmax_user@example.com",
        "is_softmax_team_member": True,
        "is_softmax_admin": True,
    }


@pytest.mark.asyncio
async def test_act_as_external_clears_admin_flag(test_client, softmax_headers: dict[str, str]) -> None:
    async with db_session() as session:
        session.add(UserSettings(user_id=get_fake_softmax_user().id, admin=True))

    response = test_client.get(
        "/admin/users",
        headers={**softmax_headers, "X-Act-As-External": "true"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "User is not a softmax team member"}
