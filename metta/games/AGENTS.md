# Creating Games in `metta/games/`

Guide for building new MettaGrid games. All game mechanics are declarative Python configs — no C++ needed.

## Quick Start

Copy the hunger game structure as a template:

```
metta/games/my_game/
    __init__.py          # Empty
    # Resources, gear, constants inlined in game/variants
    agent/               # Policy, obs parser; base AgentConfig inlined in game
    variants/seasons.py  # Season constants and food-drop events
    game.py              # MyMission(CoGameMission), make_game(), register(), site
metta/games/games.py     # Registry; import games to trigger registration
```

Tests go in `tests/metta/games/my_game/test_*.py`.

## Examples

- **Simple**: `metta/games/hunger/` — single arena, two roles, seasonal events
- **Complex**: `packages/cogames/src/cogames/games/cogs_vs_clips/` — multiple teams, territories, materialized queries,
  vibes

## Core Config Hierarchy

```
MettaGridConfig
  └── GameConfig
        ├── resource_names: list[str]       # All resources in the game
        ├── agents: list[AgentConfig]       # Per-agent configs
        ├── objects: dict[str, GridObjectConfig | WallConfig]
        ├── events: dict[str, EventConfig]  # Timestep-triggered events
        ├── actions: ActionsConfig           # move, noop, attack, change_vibe
        ├── obs: ObsConfig                  # Observation space
        ├── tags: list[str]                 # Extra tags (beyond auto type tags)
        └── materialize_queries: list[...]  # Computed tags
```

## Object Naming and MettaScope

MettaScope renders objects using the `name` field (which becomes C++ `type_name`). The sprite lookup in `worldmap.nim`
tries:

1. `objects/{name}` in the atlas
2. `objects/{stripTeamPrefix(name)}` — strips `XX:` prefix (e.g., `c:scrambler` → `scrambler`)
3. `objects/{stripTeamSuffix(name)}` — strips `_station` and `_N` suffixes

To reuse existing CvC sprites:

```python
GridObjectConfig(
    name="junction",            # MettaScope: hits junction rendering path
    map_name="plant",           # Map builder uses this to place objects
)

GridObjectConfig(
    name="scrambler_station",   # stripTeamSuffix → "scrambler" → objects/scrambler sprite
    map_name="predator_station",# Map builder key
)
```

Use `map_name` to decouple display name from map placement key.

### Visual State via Team Tags

Junctions render differently based on team tags:

- `team:cogs_green` (contains "cog") → `junction.working` sprite
- `team:clips` (contains "clip") → `junction.clipped1` sprite
- No team tag → plain `junction` sprite

Add/remove tags dynamically to reflect object state (e.g., has resources vs empty).

## Handlers

Handlers define what happens when agents interact. The `on_use_handlers` dict uses **FirstMatch** — the first handler
whose filters all pass wins, and no further handlers are tried.

```python
on_use_handlers={
    # Checked first: block agents who already have gear
    "has_gear": Handler(
        filters=[actorHasAnyOf(["scrambler", "scout"])],
        mutations=[],  # Do nothing, just block fallthrough
    ),
    # Checked second: give gear if no gear yet
    "get_gear": Handler(
        filters=[],
        mutations=[updateActor({"scrambler": 1})],
    ),
}
```

### Handler Contexts

| Handler Type      | Actor         | Target                     | Dispatch Mode                  |
| ----------------- | ------------- | -------------------------- | ------------------------------ |
| `on_use_handlers` | Agent         | Object/Agent being used    | **FirstMatch** (order matters) |
| `on_tick`         | Agent         | Agent (self)               | All matching                   |
| `aoes`            | Source object | Affected object in radius  | All matching                   |
| `events`          | N/A           | Matched by query + filters | All matching                   |

### Pattern: Conditional Mutation on Last Resource

Use two handlers with FirstMatch to branch on remaining resources:

```python
on_use_handlers={
    # First: if plant will be emptied (food <= HARVEST_AMOUNT)
    "harvest_last": Handler(
        filters=[actorHas({"scout": 1}), isNot(targetHas({"hp": HARVEST + 1}))],
        mutations=[withdraw({"hp": HARVEST}), removeTag("team:cogs_green")],
    ),
    # Second: normal harvest (food > HARVEST_AMOUNT)
    "harvest": Handler(
        filters=[actorHas({"scout": 1})],
        mutations=[withdraw({"hp": HARVEST})],
    ),
}
```

## Filters

All filters in a handler must pass (AND logic). Use `anyOf()` for OR.

```python
from mettagrid.config.handler_config import actorHas, targetHas
from mettagrid.config.filter import actorHasAnyOf
from mettagrid.config.filter.filter import isNot, anyOf

actorHas({"scrambler": 1})              # Actor has >= 1 scrambler
targetHas({"hp": 5})                    # Target has >= 5 hp
actorHasAnyOf(["scrambler", "scout"])   # Actor has either gear
isNot(targetHas({"hp": 1}))            # Target has 0 hp
anyOf([filter1, filter2])               # Either filter passes
```

## Mutations

```python
from mettagrid.config.handler_config import updateActor, updateTarget, withdraw, deposit
from mettagrid.config.mutation.tag_mutation import addTag, removeTag
from mettagrid.config.mutation.stats_mutation import logTargetAgentStat
from mettagrid.config.mutation.game_value_mutation import SetGameValueMutation

# Resources
updateActor({"hp": 10})              # Add to actor
updateTarget({"hp": -5})             # Subtract from target
withdraw({"hp": 9999})               # Transfer target → actor (up to amount)
deposit({"egg": 1})                  # Transfer actor → target

# Tags
addTag("team:cogs_green")            # Add tag to target
removeTag("team:cogs_green")         # Remove tag from target

# Stats (for rewards)
logTargetAgentStat("egg_hatched")    # Increment stat counter on target agent

# Computed values (per-tick resource conversion)
SetGameValueMutation(
    value=InventoryValue(item="energy"),
    source=InventoryValue(item="solar"),
    target=EntityTarget.ACTOR,
)  # Each tick: agent.energy += agent.solar
```

## Events

Events fire at specific timesteps and affect objects matching a query.

```python
from mettagrid.config.event_config import EventConfig, periodic
from mettagrid.config.query import query
from mettagrid.config.tag import typeTag

EventConfig(
    name="summer_regen",
    target_query=query(typeTag("junction")),  # Find all junctions
    timesteps=periodic(start=0, period=5, end=5000),
    mutations=[updateTarget({"hp": 3}), addTag("team:cogs_green")],
    max_targets=5,          # Only 5 random targets per firing
)
```

`typeTag("junction")` creates the tag `type:junction`, matching objects with `name="junction"`.

## Resource Limits and Modifiers

```python
ResourceLimitsConfig(
    min=100,                          # Base capacity
    max=65535,                        # Hard cap
    resources=["energy"],             # Which resources this limit covers
    modifiers={"scrambler": 400, "scout": 100},  # Per-item bonus
)
# Agent with 1 scrambler: effective limit = min + 400 = 500
# Agent with 1 scout: effective limit = min + 100 = 200
```

Group resources into limit categories:

```python
limits={
    "gear": ResourceLimitsConfig(min=1, max=1, resources=["scrambler", "scout"]),
    "hp": ResourceLimitsConfig(min=100, resources=["hp"]),
    "energy": ResourceLimitsConfig(min=100, resources=["energy"], modifiers={...}),
}
```

## Tags

Tags are the primary mechanism for querying and filtering entities.

- **Auto type tags**: Every object gets `type:{name}` (e.g., `type:junction`, `type:agent`)
- **Instance tags**: Set in `GridObjectConfig.tags` (e.g., `["team:cogs_green"]`)
- **Dynamic tags**: Added/removed via `addTag`/`removeTag` mutations
- **Computed tags**: `materialize_queries` for complex graph queries (see CvC)

**All tags must be declared** — either as object instance tags, auto type tags, or explicitly in `GameConfig.tags`.
Undeclared tags cause a build error.

## Map Builders

### Compound (procedural)

```python
MapGen.Config(
    width=50, height=50,
    instance=Compound.Config(
        spawn_count=10,
        hub_object="predator_station",
        corner_bundle="custom",
        corner_objects=["plant", "plant", "plant", "plant"],
        junction_object="plant",
        stations=["prey_station"],
    ),
)
```

### AsciiMapBuilder (deterministic, great for tests)

```python
AsciiMapBuilder.Config(
    map_data=[
        ["#", "#", "#", "#", "#"],
        ["#", "@", "S", ".", "#"],
        ["#", "#", "#", "#", "#"],
    ],
    char_to_map_name={"#": "wall", "@": "agent.agent", "S": "plant", ".": "empty"},
)
```

## Writing Tests

Tests live in `tests/metta/games/<game>/`. Use deterministic ASCII maps and the `Simulation` class directly.

### Test Harness Pattern

```python
from mettagrid.config.mettagrid_config import (
    ActionsConfig,
    AgentConfig,
    GameConfig,
    InventoryConfig,
    MettaGridConfig,
    MoveActionConfig,
    NoopActionConfig,
    ResourceLimitsConfig,
    WallConfig,
)
from mettagrid.mapgen.ascii import AsciiMapBuilder
from mettagrid.simulator import Simulation

def make_test_env(agent_initial, objects, events=None):
    cfg = MettaGridConfig(
        game=GameConfig(
            num_agents=1,
            max_steps=100,
            resource_names=MyConfig.RESOURCES,
            actions=ActionsConfig(noop=NoopActionConfig(), move=MoveActionConfig()),
            agent=AgentConfig(inventory=InventoryConfig(
                initial={},
                limits={"all": ResourceLimitsConfig(min=10000, max=10000, resources=MyConfig.RESOURCES)},
            )),
            objects={"wall": WallConfig(name="wall"), **objects},
            events=events or {},
            map_builder=AsciiMapBuilder.Config(
                map_data=[
                    ["#", "#", "#", "#", "#"],
                    ["#", "@", "S", ".", "#"],
                    ["#", "#", "#", "#", "#"],
                ],
                char_to_map_name={"#": "wall", "@": "agent.agent", "S": "my_object", ".": "empty"},
            ),
        )
    )
    sim = Simulation(cfg, seed=42)
    sim.agent(0).set_inventory(agent_initial)
    return sim
```

### Testing Interactions

```python
def test_scout_harvests():
    sim = make_test_env(
        agent_initial={"scout": 1, "hp": 0},
        objects={"my_object": plant_config()},
    )
    sim.agent(0).set_action("move_east")  # Move onto object
    sim.step()
    assert sim.agent(0).inventory.get("hp", 0) == 5
    sim.close()
```

### Testing Events

```python
def test_hp_drain():
    sim = make_test_env(
        agent_initial={"hp": 50},
        objects={},
        events={
            "drain": EventConfig(
                name="drain",
                target_query=query(typeTag("agent")),
                timesteps=periodic(start=0, period=10, end=100),
                mutations=[updateTarget({"hp": -1})],
            ),
        },
    )
    for _ in range(50):
        sim.agent(0).set_action("noop")
        sim.step()
    assert sim.agent(0).inventory.get("hp", 0) < 50
    sim.close()
```

### Testing Two-Agent Interactions

```python
def test_scrambler_tags_scout():
    # Agent 0 at (1,2), Agent 1 at (2,2). Agent 0 moves east onto agent 1.
    cfg = MettaGridConfig(game=GameConfig(
        num_agents=2,
        agents=[test_agent(), AgentConfig(inventory=..., rewards={})],
        # ... map with two @ symbols adjacent
    ))
    sim = Simulation(cfg, seed=42)
    sim.agent(0).set_inventory({"scrambler": 1, "hp": 0})
    sim.agent(1).set_inventory({"scout": 1, "hp": 50, "egg": 1})
    sim.agent(0).set_action("move_east")
    sim.agent(1).set_action("noop")
    sim.step()
    assert sim.agent(0).inventory["hp"] == 50  # Stole hp
    assert sim.agent(1).inventory["egg"] == 0  # Lost egg
    sim.close()
```

## Registering Your Game

### 1. Add `create` classmethod and register in `game.py`

```python
class MyMission(CoGameMission):
    @classmethod
    def create(cls, num_agents: int, max_steps: int) -> MyMission:
        return cls(name="basic", site=my_site(num_agents), num_cogs=num_agents, max_steps=max_steps)

from metta.games.games import register
register("my_game", MyMission, policy_uri="metta://policy/my_agent", policy_packages=["metta.games.my_game.agent"])
```

### 2. Add import to `metta/games/games.py`

```python
from metta.games.my_game import game  # noqa: E402, F401
```

### 3. Play it

```bash
./tools/run.py game.play game=my_game num_agents=10
```

## Common Gotchas

1. **`on_use_handlers` is FirstMatch** — handler order matters. Put guards (empty-mutation handlers) before catch-all
   handlers.

2. **`name` drives MettaScope rendering**. Use `map_name` to decouple the map placement key from the display name. Use
   `game.render.symbols` to set text-rendering symbols per object name.

3. **Tags must be declared** somewhere in the config (object tags, `GameConfig.tags`, or auto type tags). Undeclared tag
   references cause `ValueError` at build time.

4. **`typeTag("X")` creates `type:X`** — this matches the auto type tag from `GridObjectConfig.name`. If you rename
   `name`, update all `typeTag()` references.

5. **Resource limits: `min` is the base capacity**, not a floor. Modifiers add to `min`. `max` is the hard cap.

6. **Events need explicit timestep lists** — use `periodic(start, period, end)` or build lists manually.

7. **`withdraw` transfers target→actor** (pull from object to agent). `deposit` does the reverse.

8. **Nim JArray iteration** — if editing MettaScope Nim code, use `controls.getElems()` before iterating with index, not
   `for i, item in jsonArray:` (which calls `pairs()` and crashes on arrays).
