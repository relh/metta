# Planky Debugging Notes

## Session: 2025-01-29

### Goal

Improve Planky agent to achieve 100 reward in CogsGuard scrimmage.

### Current Performance

- **Mean Reward:** ~0.04 (target: 100)
- **Best Single Episode:** 1.62

---

## Critical Findings

### 1. stem=10 Policy URL Bug

When using `?stem=10`, the default explicit role counts still apply:

- Default: `miner=4, aligner=2, scrambler=4, stem=0`
- With `?stem=10`: `miner=4, aligner=2, scrambler=4, stem=10` (20 total slots!)

Since CogsGuard only has 10 agents, the first 10 role slots are used. So `stem=10` actually gives you 4 miners + 2
aligners + 4 scramblers, NOT 10 stem agents.

**Fix:** Must explicitly zero out other roles:

```bash
--policy "metta://policy/planky?miner=0&aligner=0&scrambler=0&stem=10"
```

### 2. Gear Station Interaction — Collective Resources Required

Agents reach gear stations but bumping fails when collective resources are insufficient. Gear stations use
`actorCollectiveHas(cost)` filter — the bump silently fails if resources are missing.

**Root cause:** Collective resources deplete quickly when multiple agents gear up. Agents were wasting dozens of steps
bumping stations that couldn't dispense gear.

**Fix applied:** `GetGearGoal.is_satisfied()` now checks collective resources via `_collective_can_afford()` before
walking to the station. If the collective can't afford the gear, the goal is skipped and the agent falls through to its
next goal (e.g., mining). Same fix applied to `GetHeartsGoal` (heart costs 1 of each element).

**Gear costs (from collective):**

- Miner: C1 O1 G3 S1
- Aligner: C3 O1 G1 S1
- Scrambler: C1 O3 G1 S1
- Scout: C1 O1 G1 S3

### 3. Multiple Station Positions Detected

Different agents find "miner_station" at different positions — this is normal, there may be multiple gear stations in
the hub area.

### 4. Miners Can Function Without Gear

Miners can mine without gear (just smaller cargo capacity: 4 vs 40). Now with resource-aware gear goals, miners will
attempt gear when affordable, and fall through to mining without gear when the collective can't afford it.

---

## Code Changes Made

### goals/stem.py - Role Selection

Fixed early-game role distribution:

```python
# Before: All agents became scouts when map knowledge low
# After: Distribute by agent_id
if explored_count < 50 and len(extractors) == 0:
    if agent_id < 2:
        return "miner"      # Agents 0-1
    elif agent_id < 5:
        return "aligner"    # Agents 2-4
    elif agent_id < 9:
        return "scrambler"  # Agents 5-8
    else:
        return "scout"      # Agent 9
```

### goals/gear.py - Stuck Detection

Added stuck detection and cache clearing:

- Track bump attempts at dist=1
- Clear navigator cache when stuck
- Explore randomly to find alternative path
- Reduced MAX_TOTAL_ATTEMPTS to 80, RETRY_INTERVAL to 150

### policy.py - Skip Miner Gear

Removed gear requirement for miners (they can mine without it).

---

## Diagnostic Commands

```bash
# Trace specific agent
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=3&aligner=3&scrambler=4&trace=1&trace_level=2&trace_agent=0" \
  --steps 100 --render none

# Test with wealth (bypass resource constraints)
# Edit missions.py: add wealth=100 to CogsGuardMachina1Mission
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?aligner=10" --steps 300

# Single episode with stats
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=3&aligner=3&scrambler=4" \
  --steps 200 --render none
```

---

## Next Steps to Investigate

1. **Debug gear station interaction**
   - Add logging to gear station bump handler in game layer
   - Check if `type:miner_station` tag is correct
   - Verify collective resource levels when bumping

2. **Test with wealth=100**
   - Temporarily set wealth in mission config
   - Isolate whether issue is resources vs interaction

3. **Check entity detection**
   - Print what obs_parser detects as miner_station
   - Verify only one miner_station exists in hub

4. **Compare with Nim implementation**
   - The Nim scripted agent works - what does it do differently?
   - Check how Nim handles gear station interaction

---

## Stats Reference

Key metrics to watch in scrimmage output:

- `miner.gained` - How many miners got gear
- `aligner.gained` - How many aligners got gear
- `scrambler.gained` - How many scramblers got gear
- `junction.aligned_by_agent` - Junctions captured
- `junction.scrambled_by_agent` - Enemy junctions neutralized
- `heart.gained` - Hearts acquired for combat roles
- `action.move.failed` - High = agents stuck
- `status.max_steps_without_motion` - Stuck indicator
