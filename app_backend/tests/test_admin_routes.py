from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import col, select

from metta.app_backend.database import db_session
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
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
        session.add(UserSettings(user_id="u1", admin=True))
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
        season_a = Season(name="beta-cvc", version=3, canonical=True, public=True)
        season_b = Season(name="team-trial", version=1, canonical=True, public=False)
        session.add(season_a)
        session.add(season_b)
        await session.flush()
        pool_a = Pool(
            season_id=season_a.id,
            name="qualifying",
            created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        )
        pool_b = Pool(
            season_id=season_b.id,
            name="stage-1",
            created_at=datetime(2026, 3, 8, 11, 0, tzinfo=UTC),
        )
        session.add(pool_a)
        session.add(pool_b)
        await session.flush()
        policy_versions = (
            (await session.execute(select(PolicyVersion).order_by(col(PolicyVersion.version).asc()))).scalars().all()
        )
        session.add(
            PoolPlayer(
                pool_id=pool_a.id,
                policy_version_id=policy_versions[0].id,
                created_at=datetime(2026, 3, 2, 9, 30, tzinfo=UTC),
            )
        )
        session.add(
            PoolPlayer(
                pool_id=pool_b.id,
                policy_version_id=policy_versions[1].id,
                created_at=datetime(2026, 3, 8, 11, 45, tzinfo=UTC),
            )
        )

    with patch(
        "metta.app_backend.routes.admin_routes.load_all_users",
        AsyncMock(
            return_value=[
                UserRow(
                    id="u2",
                    name="Bob",
                    email="bob@example.com",
                    created_at=datetime(2026, 2, 15, 8, 0, tzinfo=UTC),
                ),
                UserRow(
                    id="u1",
                    name="Alice",
                    email="alice@softmax.com",
                    is_softmax_team_member=True,
                    created_at=datetime(2026, 2, 1, 10, 0, tzinfo=UTC),
                ),
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
                "is_softmax_team_member": True,
                "is_softmax_admin": True,
                "discord_id": None,
                "created_at": "2026-02-01T10:00:00Z",
                "first_policy_upload_at": "2026-03-01T12:00:00",
                "last_policy_upload_at": "2026-03-05T18:30:00",
                "first_tournament_submission_at": "2026-03-02T09:30:00",
                "last_tournament_submission_at": "2026-03-08T11:45:00",
            },
            {
                "id": "u2",
                "name": "Bob",
                "email": "bob@example.com",
                "is_softmax_team_member": None,
                "is_softmax_admin": False,
                "discord_id": None,
                "created_at": "2026-02-15T08:00:00Z",
                "first_policy_upload_at": None,
                "last_policy_upload_at": None,
                "first_tournament_submission_at": None,
                "last_tournament_submission_at": None,
            },
        ]
    }


@pytest.mark.asyncio
async def test_admin_user_detail_returns_submitted_policies(test_client, softmax_headers: dict[str, str]) -> None:
    async with db_session() as session:
        session.add(UserSettings(user_id=get_fake_softmax_user().id, admin=True))
        session.add(UserSettings(user_id="u1", admin=True))
        alpha = Policy(
            name="alpha-policy",
            user_id="u1",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        beta = Policy(
            name="beta-policy",
            user_id="u1",
            created_at=datetime(2026, 3, 4, 16, 0, tzinfo=UTC),
        )
        gamma = Policy(
            name="gamma-policy",
            user_id="u1",
            created_at=datetime(2026, 3, 7, 9, 0, tzinfo=UTC),
        )
        session.add(alpha)
        session.add(beta)
        session.add(gamma)
        await session.flush()

        alpha_v1 = PolicyVersion(
            policy_id=alpha.id,
            version=1,
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        alpha_v2 = PolicyVersion(
            policy_id=alpha.id,
            version=2,
            created_at=datetime(2026, 3, 5, 18, 30, tzinfo=UTC),
        )
        beta_v1 = PolicyVersion(
            policy_id=beta.id,
            version=1,
            created_at=datetime(2026, 3, 4, 16, 0, tzinfo=UTC),
        )
        gamma_v1 = PolicyVersion(
            policy_id=gamma.id,
            version=1,
            created_at=datetime(2026, 3, 7, 9, 0, tzinfo=UTC),
        )
        session.add(alpha_v1)
        session.add(alpha_v2)
        session.add(beta_v1)
        session.add(gamma_v1)

        season_a = Season(name="beta-cvc", version=3, canonical=True, public=True)
        season_b = Season(name="team-trial", version=1, canonical=True, public=False)
        session.add(season_a)
        session.add(season_b)
        await session.flush()

        qualifying = Pool(
            season_id=season_a.id,
            name="qualifying",
            created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        )
        competition = Pool(
            season_id=season_a.id,
            name="competition",
            created_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
        )
        stage_1 = Pool(
            season_id=season_b.id,
            name="stage-1",
            created_at=datetime(2026, 3, 8, 11, 0, tzinfo=UTC),
        )
        session.add(qualifying)
        session.add(competition)
        session.add(stage_1)
        await session.flush()

        session.add(
            PoolPlayer(
                pool_id=qualifying.id,
                policy_version_id=alpha_v1.id,
                created_at=datetime(2026, 3, 2, 9, 30, tzinfo=UTC),
            )
        )
        session.add(
            PoolPlayer(
                pool_id=competition.id,
                policy_version_id=alpha_v1.id,
                created_at=datetime(2026, 3, 6, 10, 0, tzinfo=UTC),
            )
        )
        session.add(
            PoolPlayer(
                pool_id=stage_1.id,
                policy_version_id=beta_v1.id,
                created_at=datetime(2026, 3, 8, 11, 45, tzinfo=UTC),
            )
        )

    with patch(
        "metta.app_backend.routes.admin_routes.load_all_users",
        AsyncMock(
            return_value=[
                UserRow(
                    id="u1",
                    name="Alice",
                    email="alice@softmax.com",
                    is_softmax_team_member=True,
                    created_at=datetime(2026, 2, 1, 10, 0, tzinfo=UTC),
                )
            ]
        ),
    ):
        response = test_client.get("/admin/users/u1", headers=softmax_headers)

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": "u1",
            "name": "Alice",
            "email": "alice@softmax.com",
            "is_softmax_team_member": True,
            "is_softmax_admin": True,
            "discord_id": None,
            "created_at": "2026-02-01T10:00:00Z",
            "first_policy_upload_at": "2026-03-01T12:00:00",
            "last_policy_upload_at": "2026-03-07T09:00:00",
            "first_tournament_submission_at": "2026-03-02T09:30:00",
            "last_tournament_submission_at": "2026-03-08T11:45:00",
        },
        "submitted_policies": [
            {
                "id": str(beta.id),
                "name": "beta-policy",
                "created_at": "2026-03-04T16:00:00",
                "version_count": 1,
                "seasons": [
                    {
                        "season_name": "team-trial",
                        "season_version": 1,
                        "submitted_at": "2026-03-08T11:45:00",
                    }
                ],
            },
            {
                "id": str(alpha.id),
                "name": "alpha-policy",
                "created_at": "2026-03-01T12:00:00",
                "version_count": 2,
                "seasons": [
                    {
                        "season_name": "beta-cvc",
                        "season_version": 3,
                        "submitted_at": "2026-03-02T09:30:00",
                    }
                ],
            },
        ],
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
