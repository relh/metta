from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from psycopg import AsyncConnection


class TestServiceAccountRoutes:
    def test_create_list_delete_service_accounts(self, test_client: TestClient, softmax_headers: dict[str, str]):
        # Create two service accounts
        response = test_client.post("/service-accounts", json={"name": "account-1"}, headers=softmax_headers)
        assert response.status_code == 200
        sa_1 = response.json()
        assert sa_1["name"] == "account-1"

        # Tokens only returned once on create
        assert "token" in sa_1
        assert "token_hash" not in sa_1
        assert sa_1["token"].startswith("ssa_")

        assert "id" in sa_1
        id_1 = sa_1["id"]

        response = test_client.post("/service-accounts", json={"name": "account-2"}, headers=softmax_headers)
        assert response.status_code == 200
        sa_2 = response.json()
        assert sa_2["name"] == "account-2"
        id_2 = sa_2["id"]

        # IDs are distinct UUIDs
        assert id_1 != id_2
        UUID(id_1)
        UUID(id_2)

        # List returns both accounts
        response = test_client.get("/service-accounts", headers=softmax_headers)
        assert response.status_code == 200
        accounts = response.json()
        account_ids = {a["id"] for a in accounts}
        assert id_1 in account_ids
        assert id_2 in account_ids

        # Token is not exposed in list response
        for account in accounts:
            assert "token" not in account
            assert "token_hash" not in account
            assert "token_preview" in account

        # Delete the first account
        response = test_client.delete(f"/service-accounts/{id_1}", headers=softmax_headers)
        assert response.status_code == 200
        assert response.json()["id"] == id_1

        # List now only contains the second account
        response = test_client.get("/service-accounts", headers=softmax_headers)
        assert response.status_code == 200
        accounts = response.json()
        account_ids = {a["id"] for a in accounts}
        assert id_1 not in account_ids
        assert id_2 in account_ids

        # Deleting a non-existent account returns 404
        response = test_client.delete(f"/service-accounts/{id_1}", headers=softmax_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_token_hash_matches_compare_tokens(
        self, test_client: TestClient, softmax_headers: dict[str, str], stats_repo: str
    ):
        from metta.app_backend.service_accounts import compare_tokens  # noqa: PLC0415

        response = test_client.post("/service-accounts", json={"name": "hash-check"}, headers=softmax_headers)
        assert response.status_code == 200
        sa = response.json()
        sa_id = UUID(sa["id"])
        token = sa["token"]

        # Fetch the stored hash directly from the DB
        async with await AsyncConnection.connect(stats_repo) as conn:
            row = await conn.execute("SELECT token_hash FROM service_accounts WHERE id = %s", (str(sa_id),))
            record = await row.fetchone()
            assert record is not None
            stored_hash = record[0]

        assert compare_tokens(token, stored_hash)

    def test_service_account_token_authenticates(self, test_client: TestClient, softmax_headers: dict[str, str]):
        # Create a service account and grab its one-time token
        response = test_client.post("/service-accounts", json={"name": "auth-check"}, headers=softmax_headers)
        assert response.status_code == 200
        token = response.json()["token"]

        # Use the token as a Bearer token on /whoami
        token_headers = {"Authorization": f"Bearer {token}"}
        response = test_client.get("/whoami", headers=token_headers)
        assert response.status_code == 200
        # Email is synthesised from the creator's user id (debug_user_id) and their softmax membership
        assert response.json()["user_email"] == "admin+debug_user_id@serviceaccounts.softmax.com"

    def test_service_account_cannot_create_service_account(
        self, test_client: TestClient, softmax_headers: dict[str, str]
    ):
        # Create a service account and grab its one-time token
        response = test_client.post("/service-accounts", json={"name": "bot"}, headers=softmax_headers)
        assert response.status_code == 200
        token = response.json()["token"]

        # Attempt to create another service account using the service account token
        token_headers = {"Authorization": f"Bearer {token}"}
        response = test_client.post("/service-accounts", json={"name": "nested-bot"}, headers=token_headers)
        assert response.status_code == 401

    def test_service_accounts_are_user_scoped(self, test_client: TestClient, softmax_headers: dict[str, str]):
        from metta.app_backend.auth import User  # noqa: PLC0415
        from metta.app_backend.test_support.client_adapter import get_user_headers  # noqa: PLC0415

        other_user = User(id="other_user_id", email="other@softmax.com", is_softmax_team_member=True)
        other_headers = get_user_headers(other_user)

        # Create an account as the softmax user
        response = test_client.post("/service-accounts", json={"name": "softmax-account"}, headers=softmax_headers)
        assert response.status_code == 200
        sa_id = response.json()["id"]

        # Other softmax user sees an empty list (accounts are user-scoped)
        response = test_client.get("/service-accounts", headers=other_headers)
        assert response.status_code == 200
        assert response.json() == []

        # Other softmax user cannot delete the first user's account
        response = test_client.delete(f"/service-accounts/{sa_id}", headers=other_headers)
        assert response.status_code == 404
