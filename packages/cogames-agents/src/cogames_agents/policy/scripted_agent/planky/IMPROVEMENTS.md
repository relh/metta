# Planky Improvement Log

Track each improvement attempt with scrimmage scores to measure progress.

## Benchmark Command

```bash
# Standard benchmark (explicit roles, 5 episodes)
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=3&aligner=3&scrambler=4" \
  --episodes 5 --seed 42

# IMPORTANT: When using stem=10, you MUST zero out explicit roles:
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=0&aligner=0&scrambler=0&stem=10" \
  --episodes 5 --seed 42
```

---

## Critical Blockers Identified (2025-01-29)

### Blocker #1: Gear Station Interaction Fails

Agents can reach gear stations (dist=1) but bumping doesn't give them gear:

- Agent bumps station repeatedly (move_north/south/etc fails)
- Position doesn't change (correct - you bump to interact)
- But gear is never acquired
- Likely cause: collective resources depleted, or wrong station being detected

**Evidence**:

```
[t=27] GetMinerGear dist=1 → move_north (fails)
[t=28] GetMinerGear dist=1 → move_north (fails)
[t=29] GetMinerGear dist=1 → move_north (fails)
[t=30] ForceExplore kicks in, agent wanders away
```

**To Fix**: Debug the gear station interaction in the game layer, or add wealth=100 to give starting resources.

### Blocker #2: stem=10 Doesn't Override Defaults

When using `?stem=10`, the default role counts (miner=4, aligner=2, etc.) still apply. Must explicitly set
`miner=0&aligner=0&scrambler=0&stem=10` for actual stem mode.

---

## Improvement History

### Baseline

**Date**: 2025-01-29 **Config**: miner=4, aligner=2, scrambler=4 (explicit)

```
Episodes: 3, Seed: 42
Mean Reward: 0.04
Junction Aligned: 0.7
Junction Scrambled: 0.1
Miners got gear: 0.2 (2 total)
```

**Notes**: Very poor performance. Miners stuck at gear station.

---

### Attempt #1: Fix Stem Role Selection

**Date**: 2025-01-29 **Change**: Distribute roles by agent_id in early game instead of all becoming scouts

**Result**: NO CHANGE (still ~0.04 reward) **Notes**: Roles distributed correctly, but gear acquisition still broken.

---

### Attempt #2: Improve Gear Station Approach

**Date**: 2025-01-29 **Change**: Track bump attempts, try different approach sides, clear cache when stuck

**Result**: NO CHANGE **Notes**: Agent still can't get gear even when approaching from different directions.

---

### Attempt #3: Skip Miner Gear

**Date**: 2025-01-29 **Change**: Miners skip gear acquisition, mine directly (reduced cargo capacity)

```
Episodes: 5, Seed: 42
Mean Reward: 0.04
Junction Aligned: 0.9
Hearts gained: 2.5
```

**Result**: NO CHANGE **Notes**: Miners function but economy doesn't sustain combat roles. Aligners/scramblers still
need gear.

---

### Attempt #4: Resource-Aware Gear & Heart Goals

**Date**: 2025-01-28 **Change**: GetGearGoal and GetHeartsGoal now check collective resources before attempting. Agents
skip gear/heart acquisition when collective can't afford it, falling through to productive goals (mining, exploring)
instead of wasting time bumping empty stations.

Also added:

- AlignJunctionGoal/ScrambleJunctionGoal skip when agent lacks gear or heart (was bumping junctions uselessly)
- FallbackMineGoal at end of aligner/scrambler goal lists (mine when idle)
- Default role distribution changed to 6 miners / 2 aligners / 2 scramblers

```
Episodes: 20, Seed: 42, Config: stem=10 (defaults to miner=6, aligner=2, scrambler=2)
Mean Reward: ~0.25 (range 0.00-0.92)
junction.aligned_by_agent: 19.80
junction.scrambled_by_agent: 0.90
heart.gained: 30.60
```

**Result**: SIGNIFICANT IMPROVEMENT — from 0.04 baseline to ~0.25 mean reward. Junction alignments went from ~0 to 19.8
per episode average.

---

### Attempt #5: Deposit fix, nav timeout, role rebalance

**Date**: 2026-01-28

Changes:

- Fixed deposit threshold for ungeared miners (was 10, capacity is 4 — never deposited!)
- Added navigation timeout (40 steps) for aligner/scrambler junction goals
- Rebalanced default roles: 6 miners / 4 aligners / 0 scramblers
- Hub-targeted exploration for gear station discovery

```
Episodes: 20, Seed: 42, Config: stem=10
Mean Reward: ~0.93 (range 0.00-2.46)
junction.aligned_by_agent: 47.70
heart.gained: 60.80
```

**Result**: 23x improvement from baseline. Economy-first strategy works.

---

## Next Steps

1. **Reduce 0.00 episodes** — 4/20 still score zero (unfavorable map layouts?)
2. **Faster gear acquisition** — aligners wait ~80 steps for collective resources
3. **Junction defense** — aligned junctions get scrambled back by clips

## Current Best Config

```bash
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?stem=10" \
  --episodes 20 --seed 42
# Mean reward: ~0.93
```
