# Planky Improvement Plan

Iterative improvement loop for the Planky CogsGuard agent.

## The Loop

```
1. BENCHMARK  → Run scrimmage, collect baseline metrics
2. IDENTIFY   → Find the biggest weakness from metrics/observation
3. IMPLEMENT  → Make a targeted fix
4. TEST       → Run unit tests + scrimmage
5. COMMIT     → If improved, commit. If not, revert and try different approach
6. REPEAT
```

## Benchmark Command

**Default**: Use `stem=10` to let agents dynamically choose roles. Only use explicit role counts (e.g.,
`miner=4&aligner=2&scrambler=4`) when testing a specific role behavior.

```bash
# Quick debug (3 episodes, 500 steps max, ~30 sec)
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?stem=10" \
  --episodes 3 --steps 500 --seed 42

# Standard benchmark (5 episodes, ~2 min)
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?stem=10" \
  --episodes 5 --seed 42

# Full benchmark (20 episodes, ~5 min)
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?stem=10" \
  --episodes 20 --seed 42

# Testing a specific role (only when needed):
cogames scrimmage --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=10" \
  --episodes 3 --steps 500 --seed 42
```

### Key Metrics to Track

**Focus on Cog score** - ignore Clip performance, we only care about maximizing Cog outcomes.

| Metric                   | Target | Description                      |
| ------------------------ | ------ | -------------------------------- |
| `cogs.junctions` (final) | > 10   | Territory control at episode end |
| `cogs.junctions` (peak)  | High   | Best territory control achieved  |
| `Reward` (mean)          | > 15   | Average reward across episodes   |
| Resources gathered       | High   | Total resources mined/deposited  |
| Steps to first junction  | < 200  | Early game expansion speed       |

## Test Commands

```bash
# Run all planky behavior tests
metta pytest packages/cogames-agents/tests/test_planky_behaviors.py -v

# Run specific test category
metta pytest packages/cogames-agents/tests/test_planky_behaviors.py::TestPlankyMiner -v
metta pytest packages/cogames-agents/tests/test_planky_behaviors.py::TestPlankyAligner -v
metta pytest packages/cogames-agents/tests/test_planky_behaviors.py::TestPlankyScrambler -v

# Quick debug play (stem=10, limited steps)
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?stem=10&trace=1&trace_level=2" \
  --steps 300

# Debug a specific role (only when testing that role):
cogames play --mission cogsguard_machina_1.basic \
  --policy "metta://policy/planky?miner=10&trace=1&trace_level=2" \
  --steps 300
```

## Diagnostic Tips

### Testing Combat Roles Without Economy

The `CvCMission` has a `wealth` field that multiplies initial collective resources. To test aligners/scramblers without
resource constraints, temporarily edit `mission.py`:

```python
# In packages/cogames/src/cogames/cogs_vs_clips/missions.py
# Change wealth=100 for 1000 of each resource + 500 hearts
CogsGuardMachina1Mission = CvCMission(
    name="basic",
    ...
    wealth=100,  # Add this line temporarily
)
```

**IMPORTANT**: Revert this change before committing. Do NOT commit changes outside cogames-agents.

### Alternative: Use policy-level resource injection

For unit tests, the diagnostic evals in `planky_evals.py` can set up custom initial conditions.

## Score Tracking

Record improvements in `IMPROVEMENTS.md` - update it after each successful fix with scrimmage scores.

## Improvement Backlog

### Priority 1: Economy (Miners)

**Problem**: Combat roles (aligner/scrambler) can't act without hearts. Hearts require collective resources.

- [x] **1.1 Resource prioritization**: Mine the resource most needed for hearts (balanced) ✓
- [x] **1.2 Deposit efficiency**: Miners deposit when >= 50% full ✓
- [ ] **1.3 Base extractors first**: Each base corner has one extractor per resource type
  - Miners should prioritize these nearby, safe extractors initially
  - Only explore for distant extractors once base extractors are depleted
  - Benefits: short travel time, safe from enemy AOE, quick early economy
- [ ] **1.4 Dynamic role balance**: Start with more miners, shift to combat as economy stabilizes
- [ ] **1.5 Co-mining**: Miners should stay near each other for synergy bonuses
  - Extractors give bonus output when multiple agents mine together (see `synergy` field in stations.py)
  - Germanium extractors have 50% synergy bonus per additional miner
  - Miners should coordinate to arrive at extractors together
  - Consider: leader/follower pattern, or shared target selection

### Priority 2: Scrambler Targeting

**Problem**: Scramblers may chase distant junctions while closer threats expand.

- [ ] **2.1 Distance weighting**: Heavily weight distance in target selection (closer = better)
- [ ] **2.2 Threat assessment**: Prioritize junctions that are actively expanding clips territory
- [ ] **2.3 Coordination**: Multiple scramblers shouldn't target the same junction

### Priority 3: Aligner Efficiency

**Problem**: Aligners avoid AOE but may ignore good opportunities.

- [ ] **3.1 Risk/reward scoring**: Accept some AOE risk for high-value junctions
- [ ] **3.2 Cluster targeting**: Prefer junctions that would create cogs clusters
- [ ] **3.3 Follow-up coordination**: Align junctions right after scramblers neutralize them

### Priority 4: Survival & Recovery

**Problem**: Agents die in enemy AOE and lose gear/hearts.

- [ ] **4.1 Proactive retreat**: Retreat before HP hits threshold, not after
- [ ] **4.2 AOE awareness**: All roles should avoid enemy AOE, not just aligners
- [ ] **4.3 Recovery speed**: Faster gear/heart re-acquisition after death

### Priority 5: Map Control Strategy

**Problem**: No global strategy for territory expansion.

- [ ] **5.1 Hub defense**: Keep at least one junction near hub
- [ ] **5.2 Frontline awareness**: Push toward clips territory systematically
- [ ] **5.3 Pincer strategy**: Coordinate scramblers to attack clips from multiple angles

## Implementation Guide

### Adding a New Improvement

1. **Create a test first** (if behavior-testable):

   ```python
   # In test_planky_behaviors.py
   def test_new_behavior(self) -> None:
       stats = run_planky_episode(NewBehaviorMission, ...)
       assert stats["some_metric"] > threshold
   ```

2. **Create eval mission** (if needed):

   ```python
   # In planky_evals.py
   class PlankyNewBehavior(_PlankyDiagnosticBase):
       name: str = "planky_new_behavior"
       map_name: str = "new_behavior.map"
   ```

3. **Implement in goal file**:
   - `goals/miner.py` - resource gathering
   - `goals/aligner.py` - junction alignment
   - `goals/scrambler.py` - junction scrambling
   - `goals/survive.py` - HP-based retreat
   - `goals/shared.py` - cross-role behaviors (hearts)

4. **Test locally**:

   ```bash
   metta pytest packages/cogames-agents/tests/test_planky_behaviors.py -v -k "new_behavior"
   ```

5. **Benchmark**:
   ```bash
   cogames scrimmage --mission cogsguard_machina_1.basic \
     --policy "metta://policy/planky?stem=10" --episodes 5
   ```

### File Quick Reference

| File            | Purpose                                            |
| --------------- | -------------------------------------------------- |
| `policy.py`     | Entry point, role distribution, goal list creation |
| `context.py`    | PlankyContext, StateSnapshot                       |
| `entity_map.py` | Sparse map with find/query                         |
| `navigator.py`  | A\* pathfinding, exploration                       |
| `goal.py`       | Goal base class, evaluate_goals()                  |
| `goals/*.py`    | Role-specific goals                                |

## Current Baseline

Record baseline metrics here before each improvement session:

```
Date: [DATE]
Config: stem=10
Episodes: 20
Seed: 42

Results:
- Mean reward: [X]
- Mean final cogs junctions: [X]
- Peak cogs junctions: [X]
- Total resources gathered: [X]
```

## Completed Improvements

Track completed work here:

- [x] Initial goal-tree implementation
- [x] Basic role goals (miner, aligner, scrambler, scout)
- [x] Navigation with A\* pathfinding
- [x] Attempt tracking to avoid stuck loops
- [x] Aligner AOE avoidance
- [x] **Resource balancing** - Miners now prioritize the resource the collective has least of, ensuring balanced
      gathering for hearts
- [x] **Periodic re-evaluation** - Miners re-evaluate target resource every 50 steps to adapt to changing needs
- [x] **Useful action tracking** - Track steps since last useful action (mine/deposit/align/scramble) with `IDLE=N`
      indicator in trace when idle > 20 steps
- [x] **Smarter deposit threshold** - Miners only deposit when cargo >= 50% full (or >= 10 resources)
- [x] **Faster extractor failure detection** - Reduced from 5 to 3 attempts, 500 step cooldown on failed extractors
- [x] **Idle reset mechanism** - Clear navigation cache and targets after 100+ idle steps to break stuck loops

## Current Observations

After improvements, resources ARE being balanced (all 4 types mined), but:

- Junction control is poor (capture 2-3, lose all)
- Cog junctions peak early then decline - need to sustain territory
- Agents keep losing gear (walking into enemy AOE)

- [x] **Resource-aware gear/heart goals** — GetGearGoal and GetHeartsGoal check collective resources before attempting.
      Agents skip when collective can't afford, falling through to productive goals instead of wasting time bumping
      empty stations.

**Next Priority**: Economy bootstrapping — ensure miners get gear first so combat roles can follow
