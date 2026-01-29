# Planky — LLM Development Guide

## Objective

Maximize reward in CogsGuard by improving the Planky scripted agent. Reward = junction hold time. See `STRATEGY.md` for
game mechanics and role system.

## File Layout

```
planky/
  policy.py          # Multi-agent policy, role distribution defaults, per-tick brain loop
  goal.py            # Goal base class and evaluate_goals()
  context.py         # PlankyContext (state snapshot, blackboard, navigator, trace)
  navigator.py       # Pathfinding (A*, exploration, direction bias)
  entity_map.py      # Spatial memory of observed entities
  obs_parser.py      # Raw observation → StateSnapshot + visible entities
  trace.py           # Debug trace formatting
  goals/
    gear.py          # GetGearGoal base — gear acquisition with reserve checks
    miner.py         # ExploreHub, GetMinerGear, PickResource, DepositCargo, MineResource
    aligner.py       # GetAlignerGear, AlignJunction
    scrambler.py     # GetScramblerGear, ScrambleJunction
    scout.py         # GetScoutGear, Explore
    shared.py        # GetHearts, FallbackMine (used by aligner/scrambler)
    survive.py       # SurviveGoal — retreat when HP low
    stem.py          # SelectRoleGoal — dynamic role selection
  tests/
    conftest.py      # Fixtures: miner_episode, aligner_episode, etc.
    helpers.py       # run_planky_episode(), EpisodeResult
    test_miner.py    # Miner capability tests
    test_aligner.py  # Aligner capability tests
    test_scrambler.py
    test_scout.py
    test_stem.py
  STRATEGY.md        # Game mechanics, role costs, strategic loop
```

## Core Debugging Loop

This is the iteration cycle for improving Planky:

### 1. Run an episode and measure reward

```bash
uv run cogames play --mission cogsguard_machina_1.basic \
  -p planky --cogs 5 --steps 1000 --render none
```

### 2. Run with tracing to diagnose behavior

```bash
# Trace a specific agent
uv run cogames play --mission cogsguard_machina_1.basic \
  -p 'metta://policy/planky?miner=2&aligner=3&trace=1&trace_level=2&trace_agent=0' \
  --cogs 5 --steps 1000 --render none

# Trace all agents
uv run cogames play --mission cogsguard_machina_1.basic \
  -p 'metta://policy/planky?miner=2&aligner=3&trace=1&trace_level=2' \
  --cogs 5 --steps 1000 --render none
```

Trace output shows per-tick: goal chain, skipped goals (with reason), active goal, action, idle counter. Collective
resource logs print every 25 steps.

### 3. Edit goals/policy code

Each role has a goal list in `policy.py:_make_goal_list()`. Goals are evaluated in priority order. A goal's
`is_satisfied()` returns True to skip it; `execute()` returns an Action.

### 4. Validate with multi-seed sweep

```bash
# 10-seed reward sweep (copy-paste this)
total=0; for i in $(seq 1 10); do \
  r=$(uv run cogames play --mission cogsguard_machina_1.basic \
    -p planky --cogs 5 --steps 1000 --render none --seed $i 2>&1 \
    | grep "Reward" | grep -oE '[0-9]+\.[0-9]+'); \
  echo "Seed $i: $r"; total=$(echo "$total + $r" | bc); \
done; echo "Average: $(echo "scale=2; $total / 10" | bc)"
```

### 5. Run unit tests

```bash
metta pytest packages/cogames-agents/src/cogames_agents/policy/scripted_agent/planky/tests/ -v
```

Always run tests after changes. All 15 tests + 1 xfail must pass.

## Current Configuration

- **5 agents**: 2 miners, 3 aligners (set in `policy.py` defaults)
- **Mining stop**: miners idle when collective has >100 of every resource (`miner.py:COLLECTIVE_SUFFICIENT_THRESHOLD`)
- **Deposit threshold**: 50% cargo capacity (`miner.py:DepositCargoGoal`)
- **Gear reserve**: collective must have cost + 3 of each resource before buying gear (`gear.py:RESOURCE_RESERVE`)
- **Heart reserve**: collective must have 1 + 3 of each resource before buying hearts
  (`shared.py:GetHeartsGoal.RESOURCE_RESERVE`)
- **Miner gear**: no reserve requirement (miners are resource producers) but skipped when resources sufficient

## Reward Baseline

10-seed average at 1000 steps, --cogs=5: **~3.3 reward**

## Key Reward Insights

- Reward is `(aligned.junction.held / num_junctions) * (100 / max_steps)` — purely junction hold time
- Clips claims ~11 junctions and doesn't lose them (no scrambler in default config)
- More aligners = more reward, but they need miners to fund gear + hearts
- Scramblers tested poorly (1.84 avg with 2m/2a/1s) — hearts are too expensive
- Seed variance is high; always evaluate across 10+ seeds

## What to Improve

Read `STRATEGY.md` for full context. High-impact areas:

1. **Aligner junction targeting** (`goals/aligner.py:AlignJunctionGoal`) — prioritize junctions that maximize hold time
   (e.g., cluster nearby, avoid clips AOE)
2. **Dynamic role switching** — miners could become aligners once resources are sufficient instead of idling
3. **Early game economy** — first 50 steps are critical; miners need to deposit quickly so aligners get hearts
4. **Heart acquisition timing** — aligners sometimes waste time walking to chests when collective can't afford hearts
5. **Navigation efficiency** (`navigator.py`) — A\* pathfinding could be improved, agents sometimes get stuck
6. **Coordination** — multiple aligners targeting the same junction wastes effort
