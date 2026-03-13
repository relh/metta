"""Full variant: digest, seasons, carnivore, herbivore combined."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant, Deps
from metta.games.hunger.variants.carnivore import CarnivoreVariant
from metta.games.hunger.variants.digest import DigestVariant
from metta.games.hunger.variants.herbivore import HerbivoreVariant
from metta.games.hunger.variants.kids import KidsVariant
from metta.games.hunger.variants.multi_year import MultiYear5Variant


class FullVariant(CoGameMissionVariant):
    """All core mechanics: digest, seasons, carnivore, herbivore."""

    name: str = "full"
    description: str = "Digest, seasons, carnivore, herbivore."

    def dependencies(self) -> Deps:
        return Deps(required=[DigestVariant, MultiYear5Variant, CarnivoreVariant, HerbivoreVariant, KidsVariant])
