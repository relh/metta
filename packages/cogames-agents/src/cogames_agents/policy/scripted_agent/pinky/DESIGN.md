# Pinky Policy Design

Pinky is a scripted multi-agent policy for CogsGuard. Each agent is assigned a role and executes behavior-tree style
decision making.

## Current Implementation

### Roles

Roles are assigned at spawn via URI parameters (e.g., `pinky?miner=2&scout=1`).

| Role          | Risk Tolerance | Gear Bonus         | Primary Action                               |
| ------------- | -------------- | ------------------ | -------------------------------------------- |
| **MINER**     | Conservative   | +40 cargo capacity | Harvest resources, deposit at cogs buildings |
| **SCOUT**     | Aggressive     | +400 HP            | Explore map frontiers                        |
| **ALIGNER**   | Moderate       | +20 influence      | Convert neutral junctions to cogs            |
| **SCRAMBLER** | Aggressive     | +200 HP            | Neutralize enemy (clips) junctions           |

### Modes (Current)

Modes are set via `debug_info.mode` for debugging output. They describe what the agent is currently doing:

**Universal modes** (all roles):

- `retreat` - HP critical, returning to safe zone
- `get_gear` - Moving to/using role station to acquire gear
- `explore` - Random or directed exploration

**Miner-specific:**

- `mine` - Moving toward extractors
- `deposit` - Returning cargo to cogs depot

**Scout-specific:**

- `explore` - Frontier-based exploration (BFS to unexplored cells)

**Aligner-specific:**

- `get_hearts` - Acquiring hearts from chest
- `align` - Converting neutral junction to cogs

**Scrambler-specific:**

- `get_hearts` - Acquiring hearts from chest
- `scramble` - Neutralizing enemy junction

**Policy-level:**

- `activate` - Changing vibe to assigned role (step 1)
- `inactive` - Agent has non-role vibe, nooping

### State Structure (Current)

```python
@dataclass
class AgentState:
    agent_id: int
    role: Role                    # MINER, SCOUT, ALIGNER, SCRAMBLER
    vibe: str                     # Current vibe from observation
    step: int                     # Step counter

    # Position
    row: int
    col: int

    # Inventory
    energy: int
    hp: int
    carbon: int, oxygen: int, germanium: int, silicon: int
    heart: int
    influence: int

    # Gear flags
    miner_gear: bool
    scout_gear: bool
    aligner_gear: bool
    scrambler_gear: bool

    # Knowledge
    map: MapKnowledge             # Occupancy grid, structures, stations
    nav: NavigationState          # Path cache, exploration direction

    # Debug
    debug_info: DebugInfo         # mode, goal, target_object, target_pos
```

### Decision Flow (Current)

Each behavior follows a priority-based decision tree:

```
MinerBehavior.act():
  1. HP <= 15? → retreat
  2. No miner_gear? → get_gear (or explore for station)
  3. Cargo full? → deposit
  4. Otherwise → mine (move toward extractors)

ScoutBehavior.act():
  1. HP < 50? → retreat
  2. No scout_gear? → get_gear
  3. Otherwise → explore_frontier

AlignerBehavior.act():
  1. Should retreat? → retreat
  2. No aligner_gear? → get_gear
  3. No hearts? → get_hearts
  4. Otherwise → align_junction

ScramblerBehavior.act():
  1. HP < 30? → retreat
  2. No scrambler_gear? → get_gear
  3. No hearts? → get_hearts
  4. Otherwise → scramble_junction
```

### Limitations of Current Design

1. **No explicit state machine** - Mode transitions are implicit in if/else priority chains
2. **No goal/destination tracking** - Each step re-evaluates from scratch
3. **No role selection** - Roles are fixed at spawn, agents can't adapt
4. **No mood/urgency** - All decisions binary (do/don't)
5. **Debug-only modes** - Modes exist for logging, not for control flow

---

## Proposed Design

### Roles (Expanded)

| Role            | Description                              |
| --------------- | ---------------------------------------- |
| `resting`       | Inactive, waiting for assignment         |
| `choosing_role` | Evaluating team composition to pick role |
| `miner`         | Resource gathering specialist            |
| `scout`         | Map exploration specialist               |
| `aligner`       | Territory expansion specialist           |
| `scrambler`     | Enemy territory disruption specialist    |

### Modes (Explicit State Machine)

Modes should be **first-class state** that drives behavior, not just debug labels.

**Universal Modes** (available to all roles):

| Mode       | Description               | Exit Condition              |
| ---------- | ------------------------- | --------------------------- |
| `idle`     | No current task           | Goal assigned               |
| `get_gear` | Acquiring role equipment  | Gear obtained               |
| `retreat`  | Returning to safety       | HP restored above threshold |
| `explore`  | Searching for something   | Target found                |
| `move_to`  | Navigating to destination | Arrived at destination      |

**Miner Modes:**

| Mode      | Description          | Exit Condition                   |
| --------- | -------------------- | -------------------------------- |
| `harvest` | Extracting resources | Cargo full or extractor depleted |
| `deposit` | Delivering cargo     | Cargo empty                      |

**Scout Modes:**

| Mode               | Description             | Exit Condition     |
| ------------------ | ----------------------- | ------------------ |
| `frontier_explore` | BFS to unexplored areas | Map fully explored |
| `report`           | Returning with intel    | At cogs building   |

**Aligner Modes:**

| Mode             | Description                 | Exit Condition     |
| ---------------- | --------------------------- | ------------------ |
| `acquire_hearts` | Getting hearts from chest   | Have hearts        |
| `align_junction` | Converting neutral junction | Junction converted |

**Scrambler Modes:**

| Mode             | Description                 | Exit Condition       |
| ---------------- | --------------------------- | -------------------- |
| `acquire_hearts` | Getting hearts from chest   | Have hearts          |
| `raid_junction`  | Neutralizing enemy junction | Junction neutralized |

### Goals and Destinations

Explicit goal tracking separates **intent** from **execution**:

```python
@dataclass
class AgentGoal:
    """What the agent is trying to achieve."""

    # High-level intent
    goal: str                     # "get_gear", "harvest_carbon", "deposit_cargo"

    # Target
    destination: Optional[str]    # "miner_station", "carbon_extractor", "hub"
    destination_pos: Optional[tuple[int, int]]

    # Progress
    started_at_step: int
    timeout_steps: int = 100      # Give up and re-evaluate

    # Completion
    success_condition: str        # "has_miner_gear", "cargo_full", "cargo_empty"
```

### Mood / Urgency

Mood modifies behavior parameters:

| Mood        | Trigger                 | Effect                                   |
| ----------- | ----------------------- | ---------------------------------------- |
| `calm`      | HP > 80%, safe zone     | Normal risk tolerance                    |
| `cautious`  | HP 50-80% or near enemy | Reduced exploration range                |
| `urgent`    | HP 20-50%               | Prioritize retreat paths                 |
| `desperate` | HP < 20%                | Shortest path to safety, ignore all else |

### Proposed State Structure

```python
@dataclass
class AgentState:
    agent_id: int

    # Identity
    role: Role                    # resting, choosing_role, miner, scout, aligner, scrambler

    # Behavioral state machine
    mode: Mode                    # Current mode (idle, get_gear, retreat, harvest, etc.)
    mood: Mood                    # calm, cautious, urgent, desperate

    # Current goal
    goal: Optional[AgentGoal]     # What we're trying to achieve

    # ... rest of inventory, map, nav state ...
```

### State Transition Diagram

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
                    ▼                                         │
              ┌──────────┐                                    │
     spawn───►│  resting │                                    │
              └────┬─────┘                                    │
                   │ team needs role                          │
                   ▼                                          │
            ┌──────────────┐                                  │
            │choosing_role │                                  │
            └──────┬───────┘                                  │
                   │ role selected                            │
        ┌──────────┼──────────┬──────────┐                    │
        ▼          ▼          ▼          ▼                    │
    ┌───────┐ ┌───────┐ ┌─────────┐ ┌───────────┐            │
    │ miner │ │ scout │ │ aligner │ │ scrambler │            │
    └───┬───┘ └───┬───┘ └────┬────┘ └─────┬─────┘            │
        │         │          │            │                   │
        └─────────┴──────────┴────────────┘                   │
                          │                                   │
                          │ HP critical or role no longer needed
                          │                                   │
                          └───────────────────────────────────┘
```

### Role-Specific Mode Transitions

**Miner:**

```
idle ──► get_gear ──► explore ──► harvest ──► deposit ──► harvest
           │              │           │           │
           └──────────────┴───────────┴───────────┴──► retreat ──► idle
                                (HP critical)
```

**Aligner:**

```
idle ──► get_gear ──► acquire_hearts ──► align_junction ──► acquire_hearts
           │                │                  │
           └────────────────┴──────────────────┴──► retreat ──► idle
```

### Transition Triggers

| From               | To                 | Trigger                   |
| ------------------ | ------------------ | ------------------------- |
| `idle`             | `get_gear`         | Role assigned, no gear    |
| `get_gear`         | role mode          | Gear acquired             |
| any                | `retreat`          | HP < threshold for mood   |
| `retreat`          | `idle`             | HP restored, in safe zone |
| `harvest`          | `deposit`          | Cargo full                |
| `deposit`          | `harvest`          | Cargo empty               |
| `acquire_hearts`   | `align`/`scramble` | Have hearts               |
| `align`/`scramble` | `acquire_hearts`   | Hearts depleted           |
| any                | `idle`             | Goal timeout reached      |

---

## Migration Path

1. **Add `Mode` enum** with all modes (keep current logic)
2. **Add `goal` field** to AgentState
3. **Refactor behaviors** to set mode/goal explicitly
4. **Add mood system** for risk tolerance modulation
5. **Add role selection** for `choosing_role` state
6. **Add `resting`** state for unassigned agents

---

## Debug Output Format

Current: `role:mode:goal:target:action`

Proposed: `role:mode:mood:goal→dest:action`

Example: `miner:harvest:calm:get_carbon→carbon_extractor(5,12):move_east`
