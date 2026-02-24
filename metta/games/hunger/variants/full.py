"""Full variant: digest, seasons, carnivore, herbivore combined."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant


class FullVariant(CoGameMissionVariant):
    """All core mechanics: digest, seasons, carnivore, herbivore."""

    name: str = "full"
    description: str = "Digest, seasons, carnivore, herbivore."
    depends_on: list[str] = ["digest", "seasons", "carnivore", "herbivore", "kids"]
