import pytest

from metta.app_backend.database import db_session
from metta.app_backend.models.user_settings import UserSettings
from metta.app_backend.test_support.client_adapter import get_fake_softmax_user


@pytest.mark.asyncio
async def test_admin_routes_require_admin_flag(test_client, softmax_headers: dict[str, str]) -> None:
    response = test_client.get("/admin/users", headers=softmax_headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "User is not a softmax admin"}


@pytest.mark.asyncio
async def test_admin_routes_allow_admin_flag(test_client, softmax_headers: dict[str, str]) -> None:
    async with db_session() as session:
        session.add(UserSettings(user_id=get_fake_softmax_user().id, admin=True))

    response = test_client.get("/admin/users", headers=softmax_headers)

    assert response.status_code == 200
    assert response.json() == {"message": "Admin user reporting scaffold is ready for the follow-up PR."}


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
