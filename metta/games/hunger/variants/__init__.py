"""Hunger game variants."""

from metta.games.hunger.variants.carnivore import CarnivoreVariant
from metta.games.hunger.variants.digest import DigestVariant
from metta.games.hunger.variants.energy import EnergyVariant
from metta.games.hunger.variants.food import FoodVariant
from metta.games.hunger.variants.full import FullVariant
from metta.games.hunger.variants.herbivore import HerbivoreVariant
from metta.games.hunger.variants.kids import KidsVariant
from metta.games.hunger.variants.multi_year import MultiYear5Variant, MultiYear10Variant
from metta.games.hunger.variants.plants import PlantVariant
from metta.games.hunger.variants.seasons import SeasonsVariant
from metta.games.hunger.variants.solar import SolarVariant

VARIANTS = [
    DigestVariant(),
    EnergyVariant(),
    FoodVariant(),
    FullVariant(),
    KidsVariant(),
    PlantVariant(),
    HerbivoreVariant(),
    SeasonsVariant(),
    SolarVariant(),
    CarnivoreVariant(),
    MultiYear5Variant(),
    MultiYear10Variant(),
]
