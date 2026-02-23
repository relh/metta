"""Season and day/night event generation for the Hunger game."""

from __future__ import annotations

from mettagrid.config.event_config import EventConfig, periodic
from mettagrid.config.filter.filter import isNot
from mettagrid.config.handler_config import targetHas, updateTarget
from mettagrid.config.mutation.tag_mutation import addTag
from mettagrid.config.query import query
from mettagrid.config.tag import typeTag

SEASON_LENGTH = 250
YEAR_LENGTH = 1000
DAY_LENGTH = 50

FOOD_DRAIN_PERIOD = 10
STARVATION_CHECK_PERIOD = 5

# Food drops: percentage of total drain replenished per season
SEASON_FOOD_PCT: dict[str, float] = {
    "summer": 1.50,
    "fall": 0.90,
    "winter": 0.10,
    "spring": 0.90,
}

DROPS_PER_SEASON = 5
DROP_TARGET_PCT = 0.10  # fraction of plants targeted per drop

_SEASON_OFFSETS = [
    ("summer", 0),
    ("fall", SEASON_LENGTH),
    ("winter", 2 * SEASON_LENGTH),
    ("spring", 3 * SEASON_LENGTH),
]

DAY_SOLAR_DELTA = 2


def _is_daytime(tick: int) -> bool:
    return (tick % DAY_LENGTH) < (DAY_LENGTH // 2)


def _drop_timesteps(season_offset: int, num_years: int) -> list[int]:
    """5 evenly-spaced food drop timesteps within a season, across all years."""
    interval = SEASON_LENGTH // DROPS_PER_SEASON
    timesteps: list[int] = []
    for year in range(num_years):
        base = year * YEAR_LENGTH + season_offset
        timesteps.extend(base + i * interval for i in range(DROPS_PER_SEASON))
    return timesteps


def season_events(
    max_steps: int,
    num_cogs: int,
    num_plants: int,
) -> dict[str, EventConfig]:
    """Generate all seasonal, day/night, hp drain, and egg lifecycle events.

    Food balance: total drain per season = num_cogs * (SEASON_LENGTH / FOOD_DRAIN_PERIOD).
    Each season replenishes a percentage of that drain via 5 drops targeting 10% of plants.
    """
    num_years = max_steps // YEAR_LENGTH
    events: dict[str, EventConfig] = {}
    plant_query = query(typeTag("plant"))
    agent_query = query(typeTag("agent"))

    drain_per_season = num_cogs * (SEASON_LENGTH // FOOD_DRAIN_PERIOD)
    plants_per_drop = max(1, round(num_plants * DROP_TARGET_PCT))

    # --- Day/night solar cycle for agents ---
    half_day = DAY_LENGTH // 2
    events["day_solar"] = EventConfig(
        name="day_solar",
        target_query=agent_query,
        timesteps=periodic(start=0, period=DAY_LENGTH, end=max_steps),
        mutations=[updateTarget({"solar": DAY_SOLAR_DELTA})],
    )
    events["night_solar"] = EventConfig(
        name="night_solar",
        target_query=agent_query,
        timesteps=periodic(start=half_day, period=DAY_LENGTH, end=max_steps),
        mutations=[updateTarget({"solar": -DAY_SOLAR_DELTA})],
    )

    # --- Seasonal food drops ---
    for season_name, offset in _SEASON_OFFSETS:
        pct = SEASON_FOOD_PCT[season_name]
        total_food = pct * drain_per_season
        food_per_drop = total_food / DROPS_PER_SEASON
        hp_per_plant = max(1, round(food_per_drop / plants_per_drop))

        timesteps = _drop_timesteps(offset, num_years)
        events[f"{season_name}_food_drop"] = EventConfig(
            name=f"{season_name}_food_drop",
            target_query=plant_query,
            timesteps=timesteps,
            mutations=[updateTarget({"hp": hp_per_plant}), addTag("team:cogs_green")],
            max_targets=plants_per_drop,
        )

    # --- Egg lifecycle ---
    egg_drop_timesteps: list[int] = []
    egg_hatch_timesteps: list[int] = []
    for year in range(num_years):
        egg_drop_timesteps.append(year * YEAR_LENGTH + SEASON_LENGTH)  # start of fall
        egg_hatch_timesteps.append(year * YEAR_LENGTH + 3 * SEASON_LENGTH)  # start of spring

    events["egg_drop"] = EventConfig(
        name="egg_drop",
        target_query=agent_query,
        timesteps=egg_drop_timesteps,
        mutations=[updateTarget({"egg": 1})],
    )
    events["egg_hatch"] = EventConfig(
        name="egg_hatch",
        target_query=agent_query,
        timesteps=egg_hatch_timesteps,
        filters=[targetHas({"egg": 1})],
        mutations=[updateTarget({"egg": -1}), updateTarget({"kid": 1})],
    )

    # --- HP drain (continuous) ---
    events["hp_drain"] = EventConfig(
        name="hp_drain",
        target_query=agent_query,
        timesteps=periodic(start=0, period=FOOD_DRAIN_PERIOD, end=max_steps),
        mutations=[updateTarget({"hp": -1})],
    )

    # --- Starvation check: agents with egg but no hp lose the egg ---
    events["starvation_check"] = EventConfig(
        name="starvation_check",
        target_query=agent_query,
        timesteps=periodic(start=0, period=STARVATION_CHECK_PERIOD, end=max_steps),
        filters=[targetHas({"egg": 1}), isNot(targetHas({"hp": 1}))],
        mutations=[updateTarget({"egg": -1})],
    )

    return events
