# Optional Local Inter-Layer Fabric

## Scope

Subsystem: `Multiscale Cortex Core` backend

Formal reference:
- [formalization.md](../formalization.md)
- especially Section 15

Planning note:
- this workstream is an optional backend for the core formalization, not part of the first direct-stride baseline
- the direct-stride baseline does not alter the Section 15 math; it only stages a different backend first

This workstream covers the optional architecture from the substrate spec that replaces direct strided transfer with a
masked local message-passing fabric.

This is explicitly post-baseline work. The direct-stride General Agent Substrate path should land first.

## Current Code Touchpoints

- `packages/cortex/src/cortex/blocks/column/column.py`
- `packages/cortex/src/cortex/stacks/base.py`
- `packages/cortex/src/cortex/config.py`
- `agent/src/metta/agent/components/cortex.py`

The existing Column block already does expert mixing and contains an E-axis cross-attention mechanism, but it does not
implement the fabric semantics from the spec:

- explicit layer-cell lattice
- fixed receiver slot embeddings
- masked local neighborhoods across same/adjacent layers
- frozen-snapshot synchronous update over thinking step `k`

That means the fabric should be a separate backend, not a reuse of Column with a few flags.

## Design Direction

### New fabric backend

Implement a dedicated fabric stack and AgentSubstrate component path, behind an explicit config such as `execution_backend =
"direct_stride" | "local_fabric"`.

The fabric backend should preserve the same General Agent Substrate objective-routing interface as the direct-stride backend, so downstream
losses and heads continue to use the same `agent_substrate_objective_ids` or objective-context contract.

### Keep explicit `k` loop

The spec is clear that the fabric usually keeps an explicit loop over inner thinking steps while remaining parallel over
`B x T` at fixed `k`. Do not try to force this into the exact same packed-sequence execution model as the direct-stride
baseline.

### Separate private state from public interface

Each cell needs:

- private recurrent state `S`
- private output `Y`
- public interface `Z = P(Y)`

Keep these separate in config and code so the implementation matches the conceptual model.

## Work Breakdown

### 1. Define fabric configs and tensor layout

Add config objects for:

- number of cells per layer
- receiver slot embedding dimension
- public interface dimension
- neighborhood radii for lower, same, and upper layers
- retained-sequence schedule periods

Decide on the canonical tensor layout for runtime, likely one of:

- `[B, T, L, C, d]`
- `[B*T, L, C, d]`

Acceptance:

- config validates lattice sizes and neighborhood radii

### 2. Build cell wrappers and state containers

Each fabric cell should wrap an existing recurrent kernel or a new lightweight cell module while exposing:

- `Y_{t,l,j}^{(k)}`
- `S_{t,l,j}^{(k)}`
- `Z_{t,l,j}^{(k)} = P_l(Y)`

The runtime needs clean snapshot semantics so all updates at thinking step `k` read only from `k-1`.

Acceptance:

- a small synthetic test confirms synchronous update semantics

### 3. Implement the local mask builder

Build the proportional index map and the local box mask from the spec. The mask logic should support:

- same-layer neighborhoods
- lower-layer neighborhoods
- upper-layer neighborhoods
- exclusion of all other cells

Acceptance:

- mask tests confirm the exact sender sets for hand-constructed examples

### 4. Implement masked local attention and message construction

Add the attention path that:

- uses fixed receiver queries from learned slot embeddings
- derives sender keys and values from the previous public-interface snapshot
- applies the local box mask before softmax
- emits the per-cell fabric message `X`

Acceptance:

- message computation matches a reference implementation on small tensors

### 5. Implement the `k`-loop executor

At each outer step the executor should:

1. compute all public interfaces from the previous snapshot,
2. compute all masked local messages,
3. update all cells in parallel.

The executor should also support retained subsequences via stride selection over the inner thinking dimension.

Acceptance:

- the executor produces retained sequences with the expected `U_l = K / p_l` lengths

### 6. Integrate fabric outputs with General Agent Substrate heads

The fabric backend should still feed the same downstream readouts as the direct-stride General Agent Substrate path:

- RL policy/value heads
- WM route heads
- SF route heads
- the same objective-id selector interface used by the non-fabric General Agent Substrate backend

If necessary, define a small pooling or projection stage from top-layer cell outputs into route states.

Acceptance:

- downstream losses can run without knowing whether the backbone used direct stride or local fabric

### 7. Benchmark and gate rollout

Before enabling the fabric in experimental recipes, require:

- correctness parity on synthetic tests
- a local smoke training run
- throughput measurement versus the direct-stride General Agent Substrate baseline
- memory measurement at representative `K`, `L`, and `C`

## Recommended File Adds

- `packages/cortex/src/cortex/fabric/config.py`
- `packages/cortex/src/cortex/fabric/mask.py`
- `packages/cortex/src/cortex/fabric/attention.py`
- `packages/cortex/src/cortex/fabric/runtime.py`
- `agent/src/metta/agent/components/agent_substrate_fabric.py`
- `tests/cortex/test_fabric_mask.py`
- `tests/cortex/test_fabric_runtime.py`
- `tests/rl/test_agent_substrate_fabric_integration.py`

## Decision Gate

Do not start this work until the direct-stride General Agent Substrate baseline has all of the following:

- an end-to-end recipe
- parity tests for rollout versus packed training
- baseline perf measurements
- a clear reason to believe the local fabric is worth the added complexity

## Open Questions

1. Should the fabric use existing Cortex cells directly, or do we want a smaller dedicated cell API for lattice work?
2. What is the first useful neighborhood geometry for Mettagrid tasks: same-layer heavy, bottom-up heavy, or symmetric?
3. Do we want the fabric to replace only the shared lower substrate first, or the full shared-plus-routed stack in one
   step?
