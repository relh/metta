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


def parse_variants(names: list[str]) -> list:
    """Resolve variant names to instances, recursively including dependencies."""
    by_name = {v.name: v for v in VARIANTS}
    seen: set[str] = set()
    out: list = []

    def add_with_deps(name: str) -> None:
        if name in seen:
            return
        if name not in by_name:
            raise ValueError(f"Unknown variant {name!r}. Available: {', '.join(by_name.keys())}")
        seen.add(name)
        variant = by_name[name]
        deps = variant.dependencies()
        for dep_cls in deps.required:
            dep_instance = next((v for v in VARIANTS if isinstance(v, dep_cls)), None)
            if dep_instance is not None:
                add_with_deps(dep_instance.name)
        out.append(variant)

    for name in names:
        add_with_deps(name)
    return out
