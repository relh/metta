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

## Mission Defaults

The default mission (`cogsguard_machina_1.basic`) runs with:

- **8 cogs** (agents)
- **10000 max steps**
- **wealth=1** (collective starts with 10 of each resource + 5 hearts)

These are defined in `CvCMission` at `packages/cogames/src/cogames/cogs_vs_clips/mission.py`.

## Core Debugging Loop

This is the iteration cycle for improving Planky:

### 1. Run an episode and measure reward

```bash
uv run cogames play --mission cogsguard_machina_1.basic \
  -p planky --steps 10000 --render none
```

### 2. Run with tracing to diagnose behavior

```bash
# Trace a specific agent
uv run cogames play --mission cogsguard_machina_1.basic \
  -p 'metta://policy/planky?trace=1&trace_level=2&trace_agent=0' \
  --steps 10000 --render none

# Trace all agents
uv run cogames play --mission cogsguard_machina_1.basic \
  -p 'metta://policy/planky?trace=1&trace_level=2' \
  --steps 10000 --render none
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
    -p planky --steps 10000 --render none --seed $i 2>&1 \
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

- **8 agents**: 4 miners, 4 aligners (set in `policy.py` defaults; first aligner converts to scrambler at step 1000)
- **Mining stop**: miners convert to aligners when collective has >100 of every resource
  (`miner.py:COLLECTIVE_SUFFICIENT_THRESHOLD`)
- **Deposit threshold**: 50% cargo capacity (`miner.py:DepositCargoGoal`)
- **Gear reserve**: collective must have cost + 1 of each resource before buying gear (`gear.py:RESOURCE_RESERVE`)
- **Heart reserve**: collective must have 1 + 1 of each resource before buying hearts
  (`shared.py:GetHeartsGoal.RESOURCE_RESERVE`)
- **Emergency mine threshold**: activates when any collective resource < 3 (`shared.py:EmergencyMineGoal.CRITICAL_LOW`)
- **Miner gear**: no reserve requirement (miners are resource producers) but skipped when resources sufficient
- **Role defaults**: when any explicit role count is provided via URI params, unspecified roles default to 0

## Reward Baseline

10-seed average at 10000 steps, 8 cogs: **~3.2 reward** (high variance: 0.05–13.8)

## Key Reward Insights

- Reward is `(aligned.junction.held / num_junctions) * (100 / max_steps)` — purely junction hold time
- Clips claims ~11 junctions and doesn't lose them easily
- 4m/4a is the best tested config; more aligners without enough miners starves the economy
- First aligner auto-converts to scrambler at step 1000 to contest Clips junctions
- Miners auto-convert to aligners when collective resources are sufficient (>100 each)
- Seed variance is high; always evaluate across 10+ seeds

## What to Improve

Read `STRATEGY.md` for full context. High-impact areas:

1. **Reduce zero-reward seeds** — some seeds score 0.05, likely due to navigation failures or bad map layouts
2. **Navigation efficiency** (`navigator.py`) — A\* pathfinding could be improved, agents sometimes get stuck
   oscillating
3. **Aligner junction targeting** (`goals/aligner.py:AlignJunctionGoal`) — prioritize junctions that maximize hold time
   (e.g., cluster nearby, avoid clips AOE)
4. **Early game economy** — first 50 steps are critical; miners need to deposit quickly so aligners get hearts
5. **Heart acquisition timing** — aligners sometimes waste time walking to chests when collective can't afford hearts
6. **Scrambler timing** — current auto-conversion at step 1000 is fixed; could be dynamic based on Clips expansion
