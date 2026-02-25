from datetime import UTC, datetime

import pytest

from metta.app_backend.models.tournament import Season
from metta.app_backend.routes.tournament_routes import SeasonSummary


@pytest.mark.asyncio
async def test_season_summary_unknown_disabled_team_season_is_team() -> None:
    season = Season(
        name="legacy-teams-season",
        canonical=True,
        disabled_at=datetime.now(UTC),
        team_tournament_config={},
    )

    summary = await SeasonSummary.from_commissioner(season, season.name)

    assert summary.tournament_type == "team"
