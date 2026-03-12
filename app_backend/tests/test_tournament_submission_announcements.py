from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from metta.app_backend.database import db_session
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.queries import policy_queries


@pytest.mark.asyncio
async def test_manual_submission_does_not_announce_after_prior_submission(
    test_client: TestClient, regular_headers: dict[str, str]
) -> None:
    user_id = "regular@example.com"
    prior_policy_id = await policy_queries.upsert_policy(name="prior-policy", user_id=user_id, attributes={})
    prior_policy_version_id = await policy_queries.create_policy_version(
        policy_id=prior_policy_id,
        s3_path=None,
        git_hash=None,
        policy_spec={},
        attributes={},
    )
    new_policy_id = await policy_queries.upsert_policy(name="new-policy", user_id=user_id, attributes={})
    new_policy_version_id = await policy_queries.create_policy_version(
        policy_id=new_policy_id,
        s3_path=None,
        git_hash=None,
        policy_spec={},
        attributes={},
    )

    async with db_session() as session:
        prior_season = Season(name="already-submitted", canonical=True, public=True)
        session.add(prior_season)
        await session.flush()
        prior_pool = Pool(season_id=prior_season.id, name="prior-pool")
        session.add(prior_pool)
        await session.flush()
        session.add(PoolPlayer(pool_id=prior_pool.id, policy_version_id=prior_policy_version_id))
        await session.flush()

    mock_commissioner = AsyncMock()
    mock_commissioner.submit.return_value = ["entry-pool"]
    season = Season(name="beta-cvc", canonical=True, public=True)

    with (
        patch(
            "metta.app_backend.routes.tournament_routes._resolve_season_and_commissioner_or_404",
            new=AsyncMock(return_value=("beta-cvc", season, mock_commissioner)),
        ),
        patch(
            "metta.app_backend.routes.tournament_routes.announce_first_policy_submission",
            new=AsyncMock(),
        ) as mock_announce,
    ):
        response = test_client.post(
            "/tournament/seasons/beta-cvc/submissions",
            json={"policy_version_id": str(new_policy_version_id)},
            headers=regular_headers,
        )

    assert response.status_code == 200
    assert response.json() == {"pools": ["entry-pool"]}
    mock_commissioner.submit.assert_awaited_once_with(new_policy_version_id)
    mock_announce.assert_not_awaited()
