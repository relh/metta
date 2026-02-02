# Planky — Goal-Tree Scripted Agent

Planky is a goal-tree scripted policy where each agent evaluates a priority-ordered list of goals each tick. The first
unsatisfied goal decomposes into preconditions, and the deepest unsatisfied leaf produces an action.

## Quick Start

```bash
# Watch planky play a cogsguard match (GUI mode)
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky"

# Terminal mode (no GUI needed)
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky" \
  --render unicode

# Run a multi-episode scrimmage
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky" \
  --episodes 10
```

## Policy URI Parameters

Configure agent role counts and tracing via query string:

```
metta://policy/planky?miner=4&scout=0&aligner=2&scrambler=4&stem=0&trace=0
```

| Parameter     | Default | Description                                   |
| ------------- | ------- | --------------------------------------------- |
| `miner`       | 0       | Number of miner agents                        |
| `scout`       | 0       | Number of scout agents                        |
| `aligner`     | 0       | Number of aligner agents                      |
| `scrambler`   | 4       | Number of scrambler agents                    |
| `stem`        | 0       | Number of stem agents (auto-select role)      |
| `trace`       | 0       | Enable tracing (1=on)                         |
| `trace_level` | 1       | Trace verbosity: 1=minimal, 2=context, 3=full |
| `trace_agent` | -1      | Trace only this agent ID (-1=all)             |

Agents beyond the total count stay on "default" vibe (inactive/noop).

## Debugging with Tracing

### Enable trace output

```bash
# Trace all agents at level 1 (one line per tick: goal chain + action)
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=2&scrambler=2&trace=1"

# Trace only agent 0 at level 2 (shows why each goal was skipped)
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=2&scrambler=2&trace=1&trace_agent=0&trace_level=2"

# Maximum detail — level 3
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=1&trace=1&trace_agent=0&trace_level=3"
```

### Trace output format

**Level 1** — Goal chain and action:

```
[planky] [t=142 a=2 miner (105,98) hp=73] MineResource>BeNearExtractor → move_east
```

**Level 2** — Adds skip reasons, blackboard, navigation target:

```
[planky] [t=142 a=2 miner (105,98) hp=73] skip:Survive(ok) skip:GetMinerGear(ok) skip:DepositCargo(ok) → MineResource dist=13 → move_east | bb={target_resource=carbon}
```

**Level 3** — Full detail including all goal evaluations:

```
[planky] [t=142 a=2 miner (105,98) hp=73] skip:Survive(ok) skip:GetMinerGear(ok) skip:PickResource(ok) skip:DepositCargo(ok) ACTIVE:MineResource() nav_target=(110,95) → move_east bb={target_resource=carbon}
```

### Filtering trace output

Pipe through grep to focus on specific events:

```bash
# Only retreat events
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?miner=2&trace=1&trace_level=2" 2>&1 | grep Survive

# Only a specific agent
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?miner=4&trace=1" 2>&1 | grep "a=2"

# Watch goal transitions (when active goal changes)
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?miner=2&trace=1" --render log 2>&1 | grep planky
```

## Role Configurations

### Mining-heavy (resource gathering)

```bash
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?miner=6&aligner=2&scrambler=2"
```

### Balanced (default)

```bash
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?miner=4&aligner=2&scrambler=4"
```

### Combat-heavy (territory control)

```bash
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?miner=2&aligner=3&scrambler=5"
```

### With scouting

```bash
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?miner=3&scout=2&aligner=2&scrambler=3"
```

### Stem agents (auto-role selection)

```bash
cogames play -m cogsguard_machina_1.basic \
  -p "metta://policy/planky?stem=10"
```

## Alternative Policy Specification

All of these are equivalent:

```bash
# URI format
-p "metta://policy/planky?miner=4&trace=1"

# class= format with kw. prefix
-p "class=planky,kw.miner=4,kw.trace=1"

# shorthand with kw. prefix
-p "planky,kw.miner=4,kw.trace=1"
```

## Architecture Overview

```
Observation → StateSnapshot → Goal Planner → Action
                  ↓
             EntityMap update
```

Each tick:

1. Parse observation into `StateSnapshot` (source of truth — no internal drift)
2. Update sparse `EntityMap` with visible entities
3. Evaluate role's priority-ordered goal list top-down
4. First unsatisfied goal decomposes via `preconditions()` recursion
5. Deepest unsatisfied leaf calls `execute()` → returns an `Action`

### File Structure

```
planky/
├── policy.py          # PlankyPolicy + PlankyBrain (entry point)
├── context.py         # PlankyContext, StateSnapshot
├── entity_map.py      # Sparse EntityMap with find/query
├── navigator.py       # A* pathfinding, stuck detection, exploration
├── obs_parser.py      # Observation token → StateSnapshot + entities
├── goal.py            # Goal base class, evaluate_goals()
├── trace.py           # TraceLog with 3 verbosity levels
└── goals/
    ├── survive.py     # SurviveGoal (HP-based retreat)
    ├── gear.py        # GetGearGoal (generic station navigation)
    ├── shared.py      # GetHeartsGoal (used by aligner + scrambler)
    ├── miner.py       # PickResource, DepositCargo, MineResource
    ├── scout.py       # ExploreGoal, GetScoutGearGoal
    ├── aligner.py     # AlignJunctionGoal (neutral, outside enemy AOE)
    ├── scrambler.py   # ScrambleJunctionGoal (enemy, scored by blocking)
    └── stem.py        # SelectRoleGoal (heuristic role selection)
```
