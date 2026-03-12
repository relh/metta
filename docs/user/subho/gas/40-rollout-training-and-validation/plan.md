# Rollout, Training, And Validation

## Scope

Subsystem: `Exploration and Learning`

Formal reference:
- [formalization.md](../formalization.md)
- especially Sections 10, 11, 12, and 13

Planning note:
- this workstream covers how the formalized substrate is executed in rollout and minibatch training, including the
  sweep flags used to compare route combinations
- Sections 10, 11, and 12 remain the normative training equations even when early recipes stage a narrower baseline
  with intrinsic reward disabled

This workstream turns the General Agent Substrate model into a trainable system.

- rollout-time execution with outer-step carry state
- batched training with packed outer and inner axes
- replay schema changes
- optimizer and updater ordering
- recipe integration
- correctness, smoke, and perf validation

## Current Code Touchpoints

- `metta/rl/trainer.py`
- `metta/rl/trainer_config.py`
- `metta/rl/training/core.py`
- `metta/rl/training/experience.py`
- `metta/rl/training/trajectory_isolation.py`
- `metta/rl/utils.py`
- `recipes/experiment/cogsguard.py`
- `tests/rl/test_puffer_policy_forward.py`

The good news is that the current trainer already supports:

- rollout preprocess/postprocess hooks
- packed `[B * T, ...]` policy forward paths
- stateful losses
- trajectory isolation
- reward mutation before PPO advantage computation

The main new requirement is that a single outer step now contains an inner thinking sequence of length `K`, and each
AgentSubstrate layer sees a different effective sequence length `U_l`. With the updated routing preference, rollout and training
also need a stable way to thread AgentSubstrate objective ids into forward passes, much like the current routed-adapter path threads
route ids.

The user's other requirement matters here too: the trainer path should call Cortex-owned AgentSubstrate logic, not reimplement it
inside `metta/rl/training` or `metta/rl/loss`.

## Work Breakdown

### 1. Extend the replay schema for AgentSubstrate

The replay buffer needs to preserve enough information for AgentSubstrate training. At minimum that includes:

- any AgentSubstrate-specific route inputs or cached targets not recomputable from the minibatch
- any env-provided observation keys the AgentSubstrate policy actually consumes

The principle should be:

- store only what is needed for deterministic training and debugging
- avoid storing large retained sequences if they can be reconstructed cheaply during forward

Acceptance:

- an AgentSubstrate rollout can be written to replay and sampled without missing-key errors

### 2. Rollout-time execution

Rollout should keep only carry state across outer environment steps. At each outer step the `AgentSubstrate` component should:

- form per-layer inner sequences from current observations and lower-layer retained sequences
- run each AgentSubstrate layer once with its previous carry state
- emit final route states and policy outputs
- update carry state for the next outer step

The trainer loop itself should not manually unroll skipped inner microsteps.

Rollout also needs to set the AgentSubstrate objective selector consistently. Recommended baseline:

- policy-action rollout forward uses the `RL` objective id
- WM and SF auxiliary readouts that are needed during rollout postprocess either:
  - run through explicit AgentSubstrate helper heads that internally set `WM` or `SF`, or
  - consume already materialized route-family outputs from the main AgentSubstrate forward pass

Do not infer objective ids implicitly from unrelated adapter routing state.

Acceptance:

- a single environment step updates AgentSubstrate state exactly once at the trainer level
- done/truncate boundaries reset all AgentSubstrate carry states correctly
- rollout objective-id wiring is explicit and test-covered
- route-enable flags do not require separate rollout codepaths

### 3. Packed minibatch training

For training, AgentSubstrate should flatten outer time and inner time into the effective sequence axis expected by each layer.

Recommended implementation approach:

- keep the trainer's existing minibatch loop unchanged
- perform AgentSubstrate-specific pack/unpack inside Cortex AgentSubstrate runtime helpers
- use schedule-derived `U_l` to determine each layer's effective packed time length

The key parity test is:

- explicit outer-step execution over `T` steps matches the packed execution path for the same inputs and initial state
- objective-id-conditioned execution matches between explicit and packed paths

Acceptance:

- packed training and explicit-step execution agree in unit tests
- no trainer-wide special case is needed beyond AgentSubstrate-specific component/loss hooks

### 4. Order scalar updates and SF updates deterministically

The substrate defines two update paths:

- ordinary differentiable optimization of the scalar objective
- SF GTD-style updates

The training loop should document and test the exact order of:

1. policy forward
2. scalar loss accumulation and backward
3. optimizer step
4. SF auxiliary update state mutation, if separate

If the SF path ends up needing a separate optimizer or a custom no-grad update, keep that logic inside the
AgentSubstrate SF loss
rather than scattering it across the trainer.

Because the user wants loss-based routing, the training loop tests also need to lock down when a forward pass is run
under:

- `RL`
- `WM`
- `SF`

That should be derived from the active AgentSubstrate loss or explicit helper call, not from incidental loss ordering.

Acceptance:

- update ordering is explicit and covered by tests

### 5. Add recipe and config integration

Create at least one experimental recipe, likely a CogsGuard variant, that wires:

- `AgentSubstratePolicyConfig`
- AgentSubstrate losses
- WM/SF coefficients
- route-enable flags for `WM` and `SF`
- small `K` and simple schedule defaults for smoke testing
- no new env-wrapper requirements beyond the existing split action transport

Recommended file add:

- `recipes/experiment/agent_substrate_cogsguard.py`

Acceptance:

- `uv run ./tools/run.py train recipes.experiment.agent_substrate_cogsguard run=smoke ...` works locally

### 6. Add validation tiers

Required validation tiers:

- unit tests for schedule math, loss math, and reset semantics
- component parity tests between explicit outer-step unrolling and packed training execution
- selector-id parity tests for rollout and train forwards
- sweep sanity checks for `RL`, `RL + WM`, `RL + SF`, and `RL + WM + SF`
- recipe smoke test for a short local run
- checkpoint save/load smoke test
- performance measurement against a nearby non-AgentSubstrate baseline

Recommended perf comparisons:

- AgentSubstrate with `K=1` versus non-AgentSubstrate baseline
- AgentSubstrate with increasing `K`
- packed training cost as a function of `U_1`
- route split cost relative to a single-trunk architecture

### 7. Add metrics and observability

Useful rollout and training metrics:

- effective `U_l` per layer
- retained sequence lengths per layer
- actor entropy and vibe entropy
- WM and SF losses
- active route or loss flags for WM and SF
- rollout SPS and training SPS
- AgentSubstrate memory footprint if retained sequences are cached

## Recommended File Adds

- `tests/rl/test_agent_substrate_rollout_parity.py`
- `tests/rl/test_agent_substrate_packed_training.py`
- `tests/rl/test_agent_substrate_loss_id_routing.py`
- `tests/rl/test_agent_substrate_checkpointing.py`
- `tests/tools/test_agent_substrate_recipe.py`
- `recipes/experiment/agent_substrate_cogsguard.py`

## Acceptance Criteria

This workstream is complete when:

- AgentSubstrate can run a local smoke rollout/train cycle
- packed training matches explicit execution on small deterministic tests
- checkpoint save/load works
- at least one short experimental recipe is runnable end-to-end
- route-flag sweeps can disable or enable WM and SF without changing codepaths
- perf is measured before optional fabric work begins

## Risks And Mitigations

### Risk: replay bloat from retained sequences

Mitigation:

- recompute retained sequences from minibatch observations where possible
- store only irrecoverable targets and env-provided observation fields that AgentSubstrate actually consumes

### Risk: trainer complexity explodes

Mitigation:

- keep AgentSubstrate-specific packing and state handling inside Cortex AgentSubstrate modules plus thin AgentSubstrate wrappers
- preserve the existing trainer loop structure

### Risk: sequence-length blow-up when `K` is large

Mitigation:

- start with modest `K`
- benchmark layer-by-layer effective lengths before increasing schedule complexity
