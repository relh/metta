"""Multi-year variants: extend episode length for more seasonal cycles."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from metta.games.hunger.variants.seasons import YEAR_LENGTH


class MultiYear5Variant(CoGameMissionVariant):
    """5 years (5000 steps)."""

    name: str = "multi_year_5"
    description: str = "5 years (5000 steps)."
    depends_on: list[str] = ["seasons"]

    def modify_mission(self, mission) -> None:
        mission.max_steps = 5 * YEAR_LENGTH


class MultiYear10Variant(CoGameMissionVariant):
    """10 years (10000 steps)."""

    name: str = "multi_year_10"
    description: str = "10 years (10000 steps)."
    depends_on: list[str] = ["seasons"]

    def modify_mission(self, mission) -> None:
        mission.max_steps = 10 * YEAR_LENGTH
