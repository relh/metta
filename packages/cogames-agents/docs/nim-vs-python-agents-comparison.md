# Nim vs Python Scripted Agent Implementations Comparison

**Date:** 2026-01-24 **Author:** Polecat brotherhood **Issue:** mt-nim-agents

## Executive Summary

Both Nim and Python implementations exist for the CogsGuard scripted agents. The Nim version provides a
performance-optimized implementation, while the Python version offers more features and sophisticated behavior. They are
**not behaviorally equivalent** - the Python implementation is significantly more advanced.

## Comparison Table

| Agent         | Python | Nim     | Parity  | Notes                                                                              |
| ------------- | ------ | ------- | ------- | ---------------------------------------------------------------------------------- |
| **miner**     | ✓ Full | ✓ Basic | Partial | Python has HP-awareness, retry logic, safe extractor selection                     |
| **scout**     | ✓ Full | ✓ Basic | Partial | Python has frontier-based BFS exploration; Nim uses simple direction-based explore |
| **aligner**   | ✓ Full | ✓ Basic | Partial | Python has heart/influence management, retry logic; Nim is simpler                 |
| **scrambler** | ✓ Full | ✓ Basic | Partial | Python has heart acquisition, retry logic; Nim is simpler                          |
| **cogsguard** | ✓ Full | ✓ Basic | Partial | Python has multi-role coordinator, vibe system; Nim has basic vibe switching       |
| **teacher**   | ✓ Full | ✗ None  | None    | Python-only wrapper that delegates to Nim and forces initial vibes                 |

## File Locations

### Python Implementations

- **Main policy**: `packages/cogames-agents/src/cogames_agents/policy/scripted_agent/cogsguard/policy.py`
- **Miner**: `packages/cogames-agents/src/cogames_agents/policy/scripted_agent/cogsguard/miner.py`
- **Scout**: `packages/cogames-agents/src/cogames_agents/policy/scripted_agent/cogsguard/scout.py`
- **Aligner**: `packages/cogames-agents/src/cogames_agents/policy/scripted_agent/cogsguard/aligner.py`
- **Scrambler**: `packages/cogames-agents/src/cogames_agents/policy/scripted_agent/cogsguard/scrambler.py`
- **Role wrappers**: `packages/cogames-agents/src/cogames_agents/policy/cogsguard_roles.py`
- **Teacher**: `packages/cogames-agents/src/cogames_agents/policy/cogsguard_teacher.py`

### Nim Implementations

- **Main agent code**: `packages/cogames-agents/src/cogames_agents/policy/nim_agents/cogsguard_agents.nim`
- **Common utilities**: `packages/cogames-agents/src/cogames_agents/policy/nim_agents/common.nim`
- **Python wrapper**: `packages/cogames-agents/src/cogames_agents/policy/nim_agents/agents.py`

## Feature Comparison Details

### Miner Agent

| Feature                                    | Python | Nim |
| ------------------------------------------ | ------ | --- |
| Basic gather/deposit loop                  | ✓      | ✓   |
| Gear acquisition                           | ✓      | ✓   |
| HP-aware mining (return for healing)       | ✓      | ✗   |
| Safe extractor selection (avoid enemy AOE) | ✓      | ✗   |
| Action retry on failure                    | ✓      | ✗   |
| Gear re-acquisition on loss                | ✓      | ✗   |
| Extractor depletion tracking               | ✓      | ✓   |
| Corner-directed exploration                | ✓      | ✗   |

**Python LOC**: ~550 **Nim LOC**: ~100 (actMiner function)

### Scout Agent

| Feature                        | Python | Nim |
| ------------------------------ | ------ | --- |
| Basic exploration              | ✓      | ✓   |
| Gear acquisition               | ✓      | ✓   |
| Frontier-based BFS exploration | ✓      | ✗   |
| Systematic patrol fallback     | ✓      | ✗   |
| Unseen cell tracking           | ✓      | ✓   |

**Python LOC**: ~150 **Nim LOC**: ~10 (actScout function)

### Aligner Agent

| Feature                           | Python | Nim |
| --------------------------------- | ------ | --- |
| Align neutral chargers            | ✓      | ✓   |
| Gear acquisition                  | ✓      | ✓   |
| Heart/influence requirement check | ✓      | ✗   |
| Heart acquisition from chest      | ✓      | ✗   |
| Action retry on failure           | ✓      | ✗   |
| Cooldown tracking per charger     | ✓      | ✗   |

**Python LOC**: ~280 **Nim LOC**: ~15 (actAligner function)

### Scrambler Agent

| Feature                           | Python | Nim |
| --------------------------------- | ------ | --- |
| Scramble enemy chargers           | ✓      | ✓   |
| Gear acquisition                  | ✓      | ✓   |
| Heart requirement check           | ✓      | ✓   |
| Heart acquisition from chest      | ✓      | ✗   |
| Action retry on failure           | ✓      | ✗   |
| Prioritize clips-aligned chargers | ✓      | ✓   |

**Python LOC**: ~300 **Nim LOC**: ~15 (actScrambler function)

### CogsGuard Main Policy

| Feature                   | Python | Nim |
| ------------------------- | ------ | --- |
| Vibe-based role switching | ✓      | ✓   |
| Smart role coordinator    | ✓      | ✗   |
| Phase-based state machine | ✓      | ✗   |
| Detailed state tracking   | ✓      | ✓   |
| A\* pathfinding           | ✓      | ✓   |
| Map/occupancy tracking    | ✓      | ✓   |
| Structure discovery       | ✓      | ✓   |

## Which Version is Used by Default?

The default depends on how the policy is invoked:

1. **`metta://policy/cogsguard`** - Uses **Nim** implementation (`CogsguardAgentsMultiPolicy`)
2. **`metta://policy/cogsguard_py`** - Uses **Python** implementation (`CogsguardPolicy`)
3. **`metta://policy/teacher`** - Uses **Nim** implementation via `CogsguardAgentsMultiPolicy` wrapped by Python teacher
4. **`metta://policy/miner`**, **`scout`**, **`aligner`**, **`scrambler`** - Uses **Python** role-specific
   implementations

**Short name registry:**

```
cogsguard     -> Nim (CogsguardAgentsMultiPolicy)
cogsguard_py  -> Python (CogsguardPolicy)
teacher       -> Python wrapper over Nim
miner         -> Python (MinerPolicy)
scout         -> Python (ScoutPolicy)
aligner       -> Python (AlignerPolicy)
scrambler     -> Python (ScramblerPolicy)
```

## Test Coverage

Tests exist for both versions:

- `recipes/tests/test_cogsguard.py` - Integration tests
- `packages/cogames/tests/test_scripted_policies.py` - Policy tests
- `packages/cogames-agents/tests/test_cogsguard_roles.py` - Role-specific tests

## Key Differences

### Architecture

**Python:**

- Uses a `StatefulPolicyImpl` pattern with rich `CogsguardAgentState`
- Phase-based state machine (GET_GEAR, EXECUTE_ROLE)
- Separate implementation classes per role (MinerAgentPolicyImpl, etc.)
- SmartRoleCoordinator for multi-agent coordination
- Detailed debug logging support

**Nim:**

- Simpler procedural approach
- Single `CogsguardAgent` struct with all state
- Role selection via vibe-based switch statement
- Direct function calls for each role behavior

### Performance

The Nim implementation is designed for performance:

- Uses raw pointer math for observation parsing
- Minimal memory allocations
- Compiled to native code via Nim's C backend

The Python implementation prioritizes behavior sophistication:

- Rich state tracking
- Detailed error handling and retry logic
- More intelligent decision making

## Recommendations

1. **For Training (BC/RL)**: Use the **Nim** implementation via `CogsguardAgentsMultiPolicy` or the teacher wrapper -
   it's faster and the simpler behaviors may be easier to learn.

2. **For Evaluation/Testing**: Consider the **Python** implementation - its more sophisticated behavior may achieve
   better scores.

3. **Feature Development**: Add to the **Python** implementation first - it has better debug support and is easier to
   extend.

4. **Performance Critical Paths**: The **Nim** implementation can handle higher agent counts more efficiently.

## Issues Found

1. **No Nim teacher**: The teacher policy exists only in Python, though it delegates to Nim for the actual agent
   behavior.

2. **Behavioral divergence**: The two implementations will produce different behaviors in the same situations, which
   could affect training reproducibility.
