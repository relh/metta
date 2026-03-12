# Multiscale Cortex And Route Split

## Scope

Subsystem: `Multiscale Cortex Core`

Formal reference:
- [formalization.md](../formalization.md)
- especially Sections 2, 3, 4, 13, and 14

Planning note:
- this workstream owns the direct-stride interpretation of the formalization; the optional local fabric backend is
  covered separately in [50-local-fabric](../50-local-fabric/plan.md)
- if any execution shortcut in this file is narrower than the shared formalization, treat it as a staged
  implementation choice rather than a change to the math

This workstream implements the core General Agent Substrate model:

- `K` internal thinking steps per outer environment step
- layer periods `p_l` and schedule validation
- shared lower recurrent substrate through layer `L_s`
- objective-routed upper recurrent circuits for `RL`, `WM`, and `SF`
- direct-stride sequence construction via `Repeat` and `Stride`
- optional route-consistency regularization support near the split boundary

## Current Code Touchpoints

- `agent/src/metta/agent/policies/default.py`
- `agent/src/metta/agent/components/cortex.py`
- `agent/src/metta/agent/policy.py`
- `packages/cortex/src/cortex/config.py`
- `packages/cortex/src/cortex/routed_adapter.py`
- `packages/cortex/src/cortex/stacks/base.py`
- `packages/cortex/src/cortex/stacks/auto.py`
- `metta/rl/training/trajectory_isolation.py`
- `metta/rl/loss/loss.py`

The existing `CortexTD` component already manages recurrent carry across rollout and packed sequence execution across
training minibatches, but it assumes one recurrent trunk. General Agent Substrate needs per-layer schedule logic and objective-conditioned
cell routing, so this should be a new component and policy config.

## Design Direction

### New AgentSubstrate policy architecture

Create a dedicated `AgentSubstratePolicyConfig` under `agent/src/metta/agent/policies/` and a matching
`AgentSubstrate` component.
Do not bolt this onto `DefaultPolicyConfig`.

### Cortex should own the reusable routing and execution machinery

The General Agent Substrate substrate runtime, schedule operators, selector helpers, and routed-cell abstractions should live under Cortex,
not under `metta/rl`.

Recommended split:

- `packages/cortex/src/cortex/agent_substrate/`: reusable General Agent Substrate backbone execution and routing
- `agent/src/metta/agent/components/`: policy-facing adapter that calls those Cortex modules
- `metta/rl/`: trainer hooks and wrapper losses only

### Objective-routed cell selection should look like RoutedAdapter

The user requirement here is clear: shared cortex and loss-based routing should use something close to the
`RoutedAdapter` interface. The plan should therefore introduce an AgentSubstrate-specific selector path that behaves like:

- fixed slot count
- per-batch selector ids
- validation of id range and batch alignment
- explicit context or TensorDict key threading through `forward` and `step`

Recommended naming:

- `objective_ids` as the general selector tensor
- `agent_substrate_objective_ids` as the TensorDict key
- a small context helper similar to `use_route_ids(...)`

Recommended default mapping:

- all RL losses map to `RL`
- WM loss maps to `WM`
- SF loss maps to `SF`

If needed later, this can expand to finer-grained `loss_ids`, but the baseline should not create more selector slots
than the substrate actually needs.

### Keep per-layer schedule logic outside the cell implementation

The spec defines each General Agent Substrate layer as a sequence-processing recurrent operator. Reuse Cortex cells and blocks as the inner
recurrent kernel, but keep `Repeat`, `Stride`, and pack/unpack logic in a General Agent Substrate runtime module.

### Mirror adapter semantics without reusing adapter ids blindly

The existing routed-adapter path uses `route_ids` to select low-rank adapter slots. General Agent Substrate should mirror that interface
pattern, but route ids for General Agent Substrate must select routed cells or experts, not adapter matrices inside the old stack.

## Proposed Config Surface

Add Pydantic config objects for:

- `AgentSubstrateConfig`
- `AgentSubstrateLayerScheduleConfig`
- `AgentSubstrateRouteConfig`
- `AgentSubstrateObjectiveRoutingConfig`
- `AgentSubstrateConsistencyConfig`
- `AgentSubstrateExecutionConfig`

Minimum required fields:

- `num_thinking_steps` for `K`
- per-layer periods `periods`
- `split_layer`
- per-layer hidden dims or stack builders
- route names, fixed initially to `RL`, `WM`, `SF`
- per-route enable flags, with `RL` always enabled and `WM` / `SF` sweepable
- objective selector slot mapping, defaulting to `RL`, `WM`, `SF`
- whether to retain full per-layer sequences or only final states
- optional route-consistency regularizer config

Validation rules should enforce the mathematical assumptions directly:

- `p_1 <= p_2 <= ... <= p_L`
- `p_{l-1}` divides `p_l`
- each `p_l` divides `K`
- selector slots are contiguous and all configured objective names map to valid ids
- `WM` and `SF` loss flags cannot be enabled unless their corresponding route outputs are enabled

## Work Breakdown

### 1. Build sequence-operator utilities

Add reusable helpers for:

- `repeat_sequence(x, U)`
- `stride_sequence(y, stride)`
- pack/unpack between outer-time and inner-time layouts
- per-layer `U_l = K / p_l` calculation

These should live in a reusable module, not inside the policy component.

Acceptance:

- unit tests cover divisibility checks and shape transformations
- packed and unpacked helpers round-trip exactly on small synthetic tensors

### 2. Build the General Agent Substrate objective-routing interface

Add a routed-cell interface patterned after `RoutedAdapter`:

- AgentSubstrate config defines selector slot count and objective-name-to-slot mapping
- AgentSubstrate runtime validates `agent_substrate_objective_ids` shape `[B]`
- AgentSubstrate component can derive selector ids from explicit TD keys or an objective context helper
- tests verify selector-specific gradients and batch alignment exactly like routed-adapter tests do today

The baseline should support two routing granularities:

- `route_family`: coarse ids `RL`, `WM`, `SF`
- `loss_name`: optional, off by default, maps individual loss names to slots

Recommendation: implement `route_family` first and keep `loss_name` as an extension point.

Acceptance:

- routed General Agent Substrate cells accept selector ids with the same ergonomics as `RoutedAdapter`
- the selector path is independent from today's `cortex_route_ids`

### 3. Implement the shared lower tower

The shared tower should:

- take the existing env observation bundle or a pre-encoded General Agent Substrate observation bundle
- form the bottom-layer repeated sequence of length `U_1`
- execute each shared layer with its own carry state from the previous outer step
- retain the full per-step layer output sequence needed by upper layers and training losses
- expose the last element `y_t^{(l)}` for readouts and logging

Recommended implementation shape:

- one General Agent Substrate layer module per schedule level
- each General Agent Substrate layer wraps a one-layer or small-stack Cortex recurrent kernel
- carry state is stored per General Agent Substrate layer, not as one monolithic trunk state

Acceptance:

- rollout keeps only carry state across outer steps
- training can run the same shared tower on packed minibatches without custom trainer changes

### 4. Implement the objective-routed upper towers or cell banks

For the first routed layer, consume the shared boundary sequence at the appropriate stride. For later routed layers,
consume the previous routed layer's retained sequence. The key change from the earlier plan is that the routing should
be able to select cells or experts by objective id, rather than forcing one completely separate stack per objective.

Two acceptable implementations:

- separate routed cell banks behind one common interface
- one super-stack with objective-routed cells inside each routed layer

The second option is more aligned with the user's preference and should be the default design target.

Outputs to expose:

- `agent_substrate_rl_state`
- `agent_substrate_wm_state`
- `agent_substrate_sf_state`
- optionally `agent_substrate_route_layer_{route}_{l}` for loss-side diagnostics

The routed component should support config-gated execution so the same implementation can run:

- RL route only
- RL plus WM route
- RL plus SF route
- RL plus WM plus SF routes

Acceptance:

- each route produces distinct tensors with independent parameters above the split
- shapes match the schedule-derived `U_l`
- route-enable flags suppress unused route outputs cleanly without special-casing trainer code

### 5. Add split-boundary consistency support

The architecture should expose the first routed-layer outputs for `RL`, `WM`, and `SF` so a regularizer can be applied
without re-running the model.

This does not mean the regularizer is enabled by default. It only means the required tensors are available.

Acceptance:

- loss code can read routed first-layer outputs with stop-gradient on the RL target branch

### 6. Integrate serialization and checkpointing

The new policy config must round-trip through `PolicyArchitecture.to_spec()` and checkpoint/reload the General Agent Substrate recurrent
state cleanly. That includes objective-routing config and any selector-conditioned cell state.

Likely touchpoints:

- `agent/src/metta/agent/policy.py`
- AgentSubstrate component state serialization methods
- tests similar to `tests/rl/test_core_policy_serialization.py`

Acceptance:

- config spec round-trip passes
- a checkpoint reload preserves General Agent Substrate carry-state structure

### 7. Add model tests

Required tests:

- schedule validation rejects non-nested periods
- `Repeat` and `Stride` semantics are correct
- objective-routing ids validate and route the intended cell bank
- shared and routed towers produce the expected sequence lengths
- rollout-step execution and packed training execution agree on small parity cases
- route outputs are independent above `L_s`
- serialization round-trip works with AgentSubstrate config payloads

## Recommended File Adds

- `agent/src/metta/agent/policies/agent_substrate.py`
- `agent/src/metta/agent/components/agent_substrate.py`
- `packages/cortex/src/cortex/agent_substrate/config.py`
- `packages/cortex/src/cortex/agent_substrate/routed_cells.py`
- `packages/cortex/src/cortex/agent_substrate/sequence_ops.py`
- `packages/cortex/src/cortex/agent_substrate/runtime.py`
- `packages/cortex/src/cortex/agent_substrate/objective_routing.py`
- `tests/rl/test_agent_substrate_schedule_ops.py`
- `tests/rl/test_agent_substrate_objective_routing.py`
- `tests/rl/test_agent_substrate_substrate_forward.py`
- `tests/rl/test_agent_substrate_policy_serialization.py`

## Risks And Mitigations

### Risk: memory blow-up from retained sequences

Mitigation:

- retain only the sequences required by downstream routed layers and active losses
- gate debug-only intermediate tensors behind config flags

### Risk: confusion between General Agent Substrate objective ids and existing adapter route ids

Mitigation:

- reserve General Agent Substrate objective ids for General Agent Substrate cell selection only
- keep adapter slot ids under the existing `cortex_route_ids` contract
- do not reuse the same TensorDict key for both mechanisms

### Risk: trying to retrofit General Agent Substrate into `CortexTD`

Mitigation:

- keep `CortexTD` unchanged for existing recipes
- introduce a separate AgentSubstrate component with explicit per-layer state structure

### Risk: overfitting the selector interface to individual loss names too early

Mitigation:

- start with route-family ids `RL/WM/SF`
- keep a config-driven mapping from loss name to route family
- only add one-slot-per-loss routing if the coarse mapping proves too blunt
