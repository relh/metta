# Unified GameValue Design

Unify how mettagrid references numerical game state (inventory, stats, object counts, tag counts) across rewards,
observations, filters, and mutations.

## Python: GameValue Hierarchy

```python
class GameValue(Config):
    """A numerical value computed from game state."""
    pass

class InventoryValue(GameValue):
    item: str
    scope: Scope = Scope.AGENT  # AGENT or COLLECTIVE

class StatValue(GameValue):
    name: str
    scope: Scope = Scope.AGENT  # AGENT, COLLECTIVE, or GAME
    delta: bool = False

class NumObjectsValue(GameValue):
    object_type: str  # always game-scoped

class TagCountValue(GameValue):
    tag: str  # always game-scoped
```

### Helper Constructors

Short functions that parse `"scope.name"` strings:

```python
inv("gold")              -> InventoryValue(item="gold", scope=AGENT)
inv("collective.gold")   -> InventoryValue(item="gold", scope=COLLECTIVE)
stat("game.junctions")   -> StatValue(name="junctions", scope=GAME)
stat("agent.carbon.gained") -> StatValue(name="carbon.gained", scope=AGENT)
num("junction")          -> NumObjectsValue(object_type="junction")
tag("vibe:aligned")      -> TagCountValue(tag="vibe:aligned")
```

Default scope is AGENT for `inv()` and `stat()`. `num()` and `tag()` are always game-scoped.

## Python: Usage Sites

### Rewards

```python
class AgentReward(Config):
    nums: list[GameValue]
    denoms: list[GameValue]
    weight: float = 1.0
    max: float | None = None
```

Existing helpers (`inventoryReward()`, etc.) become thin wrappers.

### Observations

```python
class GlobalObsConfig(Config):
    ...
    value_obs: list[GameValue] = []  # replaces stats_obs: list[StatsValue]
```

Any GameValue can be observed, not just stats.

### Filters

```python
class GameValueFilter(Filter):
    value: GameValue
    min: int = 0
    target: HandlerTarget = HandlerTarget.ACTOR
```

Replaces `ResourceFilter`. Can filter on any readable GameValue.

### Mutations

```python
class SetGameValueMutation(Mutation):
    value: InventoryValue | StatValue  # only mutable types
    delta: int
    target: EntityTarget = EntityTarget.ACTOR
```

Replaces `ResourceDeltaMutation` and `StatsMutation`. `num()` and `tag()` are read-only.

## Python: C++ Conversion

New file `config/mettagrid_c_value_config.py`:

```python
def resolve_game_value(gv: GameValue, mappings: dict) -> CppGameValueConfig:
    """Convert any GameValue to C++ config with integer IDs."""
    if isinstance(gv, InventoryValue):
        return CppGameValueConfig(
            type=INVENTORY,
            id=mappings["resource_name_to_id"][gv.item],
            scope=convert_scope(gv.scope))
    elif isinstance(gv, StatValue):
        return CppGameValueConfig(
            type=STAT,
            id=mappings["stat_name_to_id"][gv.name],
            scope=convert_scope(gv.scope),
            delta=gv.delta)
    elif isinstance(gv, NumObjectsValue):
        tag_name = typeTag(gv.object_type)
        return CppGameValueConfig(
            type=TAG_COUNT,
            id=mappings["tag_name_to_id"][str(tag_name)])
    elif isinstance(gv, TagCountValue):
        return CppGameValueConfig(
            type=TAG_COUNT,
            id=mappings["tag_name_to_id"][gv.tag])
```

## C++: GameValueConfig

All values resolved to integer IDs at config time:

```cpp
enum class GameValueType : uint8_t { INVENTORY, STAT, TAG_COUNT };
enum class GameValueScope : uint8_t { AGENT, COLLECTIVE, GAME };

struct GameValueConfig {
    GameValueType type;
    GameValueScope scope;
    uint16_t id;        // resource_id, stat_id, or tag_id
    bool delta = false;
};
```

## C++: ResolvedGameValue

At init time, resolve config into direct pointers:

```cpp
struct ResolvedGameValue {
    GameValueType type;
    bool delta;
    float* value_ptr;      // direct pointer into StatsTracker/Inventory/TagIndex storage
    float prev_value = 0;  // for delta tracking
};
```

`RewardComputer::init()` resolves each `GameValueConfig` into a `ResolvedGameValue` pointing directly into the
appropriate storage. `compute()` becomes pure pointer dereferences with no map lookups.

## C++: StatsTracker Changes

Replace `unordered_map<string, float>` with:

```cpp
class StatsTracker {
    std::vector<float> values;                    // indexed by stat_id, pre-reserved
    std::unordered_map<std::string, uint16_t> name_to_id;  // for on-the-fly creation

    float* get_ptr(uint16_t stat_id);             // direct pointer for ResolvedGameValue
    uint16_t get_or_create(const std::string& name);  // append on demand
};
```

Pre-reserve capacity at init so pointers into `values` remain stable (no reallocation).

## C++: Unified Filter and Mutation

```cpp
// Replaces ResourceFilter + can filter on any GameValue
struct GameValueFilter : Filter {
    ResolvedGameValue value;
    float threshold;
    bool passes(const HandlerContext& ctx) const override;
};

// Replaces ResourceDeltaMutation + StatsMutation
struct GameValueMutation : Mutation {
    ResolvedGameValue target;  // must be INVENTORY or STAT
    float delta;
    void apply(HandlerContext& ctx) override;
};
```

## Files Changed

### New files

- `packages/mettagrid/python/src/mettagrid/config/game_value.py`
- `packages/mettagrid/python/src/mettagrid/config/mettagrid_c_value_config.py`

### Modified files

- `config/reward_config.py` — use GameValue, remove old types
- `config/obs_config.py` — `value_obs: list[GameValue]` replaces `stats_obs`
- `config/filter/` — add `GameValueFilter`
- `config/mutation/` — add `SetGameValueMutation`
- `config/mettagrid_c_config.py` — use `resolve_game_value()`
- `cpp/include/mettagrid/objects/reward_config.hpp` — use `GameValueConfig`
- `cpp/include/mettagrid/objects/agent.hpp` / `agent.cpp` — use `ResolvedGameValue`
- `cpp/include/mettagrid/stats_tracker.hpp` — vector-based storage with pre-reserve
- `cpp/include/mettagrid/handler/filters/` — add `GameValueFilter`
- `cpp/include/mettagrid/handler/mutations/` — add `GameValueMutation`

## Constraints

- `num()` and `tag()` are read-only (game-scoped, not valid as mutation targets)
- `inv()` and `stat()` are mutable
- Scope is a field on the value, not separate subclasses
- StatsTracker pre-reserves capacity so float pointers remain stable
- All string-to-id resolution happens at config/init time, never at runtime
