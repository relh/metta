# Investigation: aligned.junction.held Scoring Gap (300 vs 30k)

## Summary

The 100x scoring gap (PPO: ~300 vs expected: ~30,000) for `aligned.junction.held` is caused by a fundamental energy
starvation problem that prevents agents from effectively navigating and completing their roles.

## Key Findings

### 1. Scripted Agents Are NOT Successfully Aligning Junctions

After running `cogames play` with both the Nim (`metta://policy/role`) and Python (`metta://policy/role_py`) policies, I
observed:

- **clips.aligned.junction.held: ~135,000** (over 5000 steps)
- **cogs.aligned.junction.held: 0** (zero junctions aligned to cogs)

This means the scripted agents themselves are failing to align junctions, just like PPO.

### 2. Root Cause: Energy Starvation

Agents are experiencing severe energy starvation:

| Metric                     | Expected | Observed                  |
| -------------------------- | -------- | ------------------------- |
| action.move.failed         | ~0%      | ~99%                      |
| action.move.success        | ~99%     | ~1%                       |
| max_steps_without_motion   | low      | ~2900 (out of 3000 steps) |
| energy.gained (3000 steps) | ~300,000 | ~130-200                  |

### 3. Why Energy is Depleted

The game is designed with an energy-based economy:

- **Move action costs**: 3 energy per move
- **Agent initial energy**: 100
- **Base energy regen**: +1 energy/tick
- **Assembler AOE (expected)**: +100 energy/tick to cogs agents within range 10

**Problem**: The assembler's AOE energy buff is NOT being applied to agents.

In testing, I observed:

- Agent spawns at (26, 26), assembler at (29, 29) - distance 6 (within AOE range 10)
- Agent starts with 100 energy
- After 1 step: energy = 10 (dropped 90!)
- Expected: energy should increase to 200+ from AOE

### 4. The Junction Alignment Flow

To align a junction, agents must:

1. **Scrambler** scrambles clips-aligned junctions to neutral
   - Requires: scrambler gear + 1 heart
   - Must navigate to junction and bump into it

2. **Aligner** aligns neutral junctions to cogs
   - Requires: aligner gear + 1 influence + 1 heart
   - Must navigate to junction and bump into it

**Problem**: Agents can't navigate because they don't have energy to move.

### 5. Chicken-and-Egg Problem

The game design creates a catch-22:

- Agents need energy to move to junctions
- Junctions provide energy AOE when aligned to cogs
- But junctions start aligned to clips (enemy)
- The assembler should provide energy, but its AOE isn't working

## Configuration Details

### Agent Energy Config

```python
inventory.limits = {'energy': ResourceLimitsConfig(min=10, max=65535, ...)}
inventory.initial = {'energy': 100}
inventory.regen_amounts = {'default': {'energy': 1, 'hp': -1, 'influence': -1}}
```

### Move Action Cost

```python
actions.move = MoveActionConfig(consumed_resources={'energy': 3})
```

### Assembler AOE (Hub)

```python
aoes = [
    AOEEffectConfig(
        range=10,
        resource_deltas={'influence': 10, 'energy': 100, 'hp': 100},
        filters=[isAlignedToActor()]  # Same collective
    ),
    AOEEffectConfig(
        range=10,
        resource_deltas={'hp': -1, 'influence': -100},
        filters=[isEnemy()]  # Different collective
    )
]
```

### Junction AOE

Same structure as assembler, but junctions are clips-aligned, so they:

- Give +100 energy to clips agents
- Deal -1 hp to cogs agents

## Recommendations

1. **Investigate AOE Application Bug**: The assembler's energy AOE is not being applied to cogs agents. Check if there's
   a bug in the collective alignment matching for AOE effects.

2. **Reduce Move Energy Cost**: Consider lowering from 3 to 1 or 2 to make agents more mobile.

3. **Increase Base Energy Regen**: Increase from +1 to +5 or +10 per tick.

4. **Give Agents Initial Hearts**: Currently agents start with 0 hearts and must get them from chests, but they can't
   reach chests without energy.

5. **Check Scripted Agent Logic**: The Nim agents may have bugs in their pathfinding or role execution that cause them
   to get stuck even when they have energy.

## Test Commands Used

```bash
# Run with teacher policy (uses Nim backend)
uv run tools/run.py cogsguard.play "policy_uri=metta://policy/teacher" render=log max_steps=3000

# Run with Python policy
uv run tools/run.py cogsguard.play "policy_uri=metta://policy/role_py" render=log max_steps=3000

# Check simulation state
uv run python -c "
from mettagrid.simulator.simulator import Simulator
from recipes.experiment.cogsguard import make_env
cfg = make_env(num_agents=10, max_steps=100)
sim = Simulator().new_simulation(cfg, seed=42)
# ... inspect state
"
```

## 2026-01-27 Follow-up: 1000-step scripted runs (seed 42)

This follow-up rechecked scripted agents on a single 1000-step `recipes.experiment.cogsguard` episode and compared the
full evaluation pipeline (`tools/run.py evaluate`) with the debug harness
(`packages/cogames-agents/scripts/run_cogsguard_rollout.py`).

### 1) EvaluateTool results (max_steps=1000, max_workers=1)

For each policy, we extracted `collective.cogs["aligned.junction.held"]` and `collective.clips["aligned.junction.held"]`
from the episode stats. The cogs key is missing and effectively zero in all cases, while clips continues to accumulate
junction hold time.

| policy_uri              | cogs.aligned.junction.held | clips.aligned.junction.held |
| ----------------------- | -------------------------- | --------------------------- |
| metta://policy/wombo    | 0.00                       | 35033.00                    |
| metta://policy/role     | 0.00                       | 37000.00                    |
| metta://policy/role_py  | 0.00                       | 29023.00                    |
| metta://policy/alignall | 0.00                       | 28021.00                    |
| metta://policy/teacher  | 0.00                       | 36022.00                    |

### 2) Debug harness instrumentation

The debug harness gives role/gear/structure visibility that the eval pipeline does not.

#### wombo (metta://policy/wombo)

- aligner: 0 align attempts
- scrambler: 3 scramble attempts
- gear station use is mostly without resources (e.g., aligner 1055 uses, 1 with resources)
- gear resource windows are rare (8-16 steps total), and even rarer when a role is adjacent (0-4 steps)

#### role_py with miner-heavy ratio

Command:

```bash
uv run packages/cogames-agents/scripts/run_cogsguard_rollout.py \
  --steps 1000 --max-steps 1000 --seed 42 --agents 10 \
  --policy-uri 'metta://policy/role_py?miner=5&scout=1&aligner=2&scrambler=2' \
  --allow-missing-roles
```

Findings:

- miners: 32 mine attempts, 29 deposits
- aligner: 29 align attempts, 0 mismatches
- scrambler: 4 scramble attempts
- gear station use is still mostly without resources (aligner 970 uses, 1 with resources)
- resource windows are short (17-21 steps) with limited adjacency (0-4 steps)

#### Note on Nim role policy

The Nim `metta://policy/role` policy does not expose per-agent `_state` to the harness, so role-level instrumentation
appears empty. Use `role_py` for detailed instrumentation.

### 3) Interpretation

These 1000-step runs still point to resource/coordination starvation (gear resource windows and adjacency are rare),
rather than purely insufficient miner counts.

### 4) Future plans / next debug targets

- Instrument why resource windows are so brief (collective inventory deltas vs gear costs) and whether miners are
  depositing in the right chest/collective bucket.
- Check if role agents are reaching the right stations when resources are available (trace adjacency timing).
- Verify whether align/scramble actions require additional prerequisites (hearts/influence) that remain starved.
- Compare 1000-step vs 3000-step runs to see if longer horizons meaningfully increase cogs alignment.
- Add a small experiment that forces fixed role ratios in `wombo` (or a targeted policy) to isolate role-mix effects.

## Additional failure modes observed across scripted agents

These are inferred from the 1000-step evals plus the debug harness runs. Each bullet is a distinct failure mode that can
block `cogs.aligned.junction.held`, regardless of role mix.

1. **Resource windows are too short and poorly aligned with role adjacency**
   - Gear station usage is dominated by attempts without resources.
   - Resource windows exist but are brief, and the right role is rarely adjacent during those windows.
   - Outcome: role agents fail to equip, so alignment actions never trigger.

2. **Aligner/scrambler action rate is extremely low**
   - Even with role_py and miner-heavy ratios, align/scramble attempts are sparse.
   - Outcome: junctions remain clips-aligned, so cogs never get junction hold credit.

3. **Role thrash / non-concurrent roles**
   - In role_py, the “agents=10” count reflects agents spending time in that role at some point, not concurrent role
     assignment. This suggests roles may be cycling without sustained role coverage.
   - Outcome: miners/aligners/scramblers are not reliably present at the same time to complete the multi-step flow.

4. **Instrumentation visibility mismatch (Nim vs Python)**
   - Nim `role` policy does not expose `_state`, so debug harness visibility is limited. This can mask state/role
     misbehaviors in the Nim path.
   - Outcome: we may be missing a Nim-specific failure mode (pathing/role execution), distinct from Python behavior.

5. **Potential prerequisites beyond gear (hearts/influence)**
   - Aligner requires aligner gear + influence + heart. Scrambler requires scrambler gear + heart.
   - The debug harness does not currently verify these prerequisites at the moment of action.
   - Outcome: actions may fail even with gear, if hearts/influence are starved.

## Definitive next steps (3–5 experiments to disambiguate causes)

These are designed to be decisive; each should either confirm a root cause or eliminate it.

1. **Resource window tracing (collective inventory deltas)**
   - Add a short-lived trace that logs collective resource levels each tick plus gear station attempts.
   - Goal: confirm whether resources are actually available when agents are adjacent and whether deposits are hitting
     the correct collective bucket.

2. **Action prerequisite audit (hearts/influence at action time)**
   - Instrument align/scramble attempts to log inventory state (gear, hearts, influence).
   - Goal: determine if action failures are due to missing hearts/influence versus pathing/targeting.

3. **Concurrent role coverage audit**
   - Track per-tick role counts and role transitions for role_py/wombo.
   - Goal: measure how often the miner + scrambler + aligner roles are simultaneously staffed for >N steps.

4. **Nim vs Python parity check**
   - Run the same scenario with `role` (Nim) vs `role_py`, capturing only metrics available to both (e.g., action
     counts, movement success).
   - Goal: isolate Nim-specific logic or pathing regressions that don’t exist in Python.

5. **Long-horizon comparison (1000 vs 3000 steps)**
   - Repeat the 1000-step runs at 3000 steps to determine if time horizon is the limiting factor.
   - Goal: verify whether alignment is simply delayed versus fundamentally blocked.

## Related Files

- `packages/cogames/src/cogames/cogs_vs_clips/mission.py` - CogsGuard mission config
- `packages/cogames/src/cogames/cogs_vs_clips/stations.py` - Junction and Hub configs
- `packages/cogames-agents/src/cogames_agents/policy/nim_agents/cogsguard_agents.nim` - Nim scripted agents
- `packages/cogames-agents/src/cogames_agents/policy/scripted_agent/cogsguard/` - Python scripted agents
- `recipes/experiment/cogsguard.py` - Recipe for running CogsGuard
