# 0011: Planky Nim Port

## Goal

Add a Nim-backed policy entrypoint, `metta://policy/planky_nim`, that tracks the Python `planky` scripted policy
interface (URI parameters, role distribution semantics, and eventually decision logic), so we can run Planky as a Nim
agent without changing downstream tooling (CoGames CLI, training supervisors, evaluators).

This spec documents:

- What shipped in the initial wiring and what shipped as the full port
- The intended architecture (Nim module split) for parity with Python `planky`
- Remaining gaps (if any) and how to test for them

## Current State (This PR)

We add a Nim Planky policy exported via the existing `nim_agents` bindings and wire it up as a selectable policy:

- `PlankyPolicy` (Nim) is exported and wired up as `cogames_agents.policy.nim_agents.agents.PlankyAgentsMultiPolicy`
  with `short_names = ["planky_nim"]`.
- The init config supports the main Python `planky` URI knobs (role counts + `stem`, trace, and role switching):
  - `miner`, `scout`, `aligner`, `scrambler`, `stem`
  - `disable_role_switching`
  - `trace`, `trace_level`, `trace_agent`
- Role distribution semantics match Python `planky`:
  - Default (no explicit roles, no stem): `miner=4, aligner=4, scrambler=0`
  - If `stem>0` or any explicit role is provided, unset roles default to 0
  - Team role list is tiled to cover `num_agents`
  - "First aligner converts to scrambler at step 1000" is implemented (unless role switching is disabled)

Behavior and tooling parity shipped in this PR:

- Observation snapshot parity: build a `StateSnapshot` from observation tokens in Nim.
- Navigator parity: direction-biased exploration, sidestep behavior, stuck detection, and greedy fallback aligned with
  Python.
- Goal tree parity: full role goal sets ported (miner, scout, aligner, scrambler, stem) plus shared goals.
- Tracing parity: `trace`, `trace_level`, `trace_agent` gate per-step trace lines.
- Renderer/debug metadata parity: publish per-step `policy.infos` matching Python (`role`, `goal`, `target`, optional
  `mining`, and always `cargo`).

## Full Parity Target (What "Planky in Nim" Means)

Python `planky` is a goal-tree policy with:

- Per-agent persistent state (blackboard, role, gear tracking, navigation targets)
- Observation parsing into a richer state snapshot (entities, inventories, charger state, deposits, junction control)
- A\* navigation + replanning
- Priority-ordered goal evaluation with tracing and debugging output
- Policy-level role distribution + selective role switching behavior

Full Nim parity should reproduce:

1. URI / init config behavior:
   - Same parameters and defaults, including the "stem overrides defaults unless roles set" rule.
2. Role-specific behavior:
   - Miner: gear, resource targeting, mine/deposit loop, fallback mining.
   - Aligner: gear, junction selection, avoid AOE, hearts acquisition, alignment actions.
   - Scrambler: gear, target enemy junctions, scramble actions.
   - Scout: gear, exploration policy.
   - Stem: dynamic role selection policy.
3. Tracing parity:
   - Trace gating (`trace`, `trace_level`, `trace_agent`) and comparable log lines for debugging and evaluation.
4. Tests parity:
   - Port the deterministic Planky eval missions (or reuse the same missions) and assert expected behaviors.

## Proposed Nim Architecture

### Data Model

Mirror the Python module split, but kept Nim-idiomatic:

- `planky_types.nim`
  - `PlankyConfig` (URI/init params)
  - `PlankyAgentState` (persistent)
  - `StateSnapshot` (parsed observation)
- `planky_obs_parser.nim`
  - Observation tokens -> typed snapshot + spatial entity map
- `planky_nav.nim`
  - A\* / BFS with cached passability, path compression
- `planky_goals.nim`
  - Goal tree types + evaluator + goal implementations (miner/aligner/scrambler/scout/shared)
- `planky_policy.nim`
  - Multi-agent wrapper, role distribution, per-agent brains, trace plumbing

### Integration

- Export a single `PlankyPolicy` ref object from `nim_agents.nim` with `newPlankyPolicy(string)` and `stepBatch(...)`.
- Keep init config as JSON:
  - `{ "env": <PolicyEnvInterface JSON>, "planky": <PlankyConfig> }`
- Keep Python wrapper class in `packages/cogames-agents` only as:
  - URI parameter mapping + constructing init JSON + subclassing `NimMultiAgentPolicy`

### Incremental Port Plan

1. Stabilize interface + wiring (done in this PR).
2. Port observation parsing + state snapshot (done in this PR).
3. Port navigation (done in this PR).
4. Port goal evaluation (done in this PR).
5. Port role switching + stem behavior (done in this PR).
6. Match tracing + infos enough for tooling parity (done in this PR).
7. Remaining work (if any): identify subtle behavioral divergences via side-by-side `cogames play` comparisons and add
   targeted regression tests.

## Non-Goals

- Performance tuning beyond "not obviously slow" until parity is achieved.
- Backwards-compat shims between config formats; `planky_nim` is a new entrypoint.
