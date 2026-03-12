# Environment And Observation Contracts

## Scope

Subsystem: `Sensorimotor Interface`

Formal reference:
- [formalization.md](../formalization.md)
- especially Sections 1, 5, 6, 7, and 10

Planning note:
- this workstream implements the env boundary implied by the formalization, while keeping vibe-observation effects
  inside the environment for the baseline implementation plan
- Sections 6, 7, and 10 of the formalization remain the mathematical target; env-side vibe handling and deferred reward
  shaping are baseline staging choices only

This workstream covers the parts of the substrate that touch the environment boundary:

- outer environment time and per-agent observations
- dual task/vibe actions
- the assumption that vibe-action effects stay inside the env or recipe path
- rollout and evaluation adapters that keep these contracts consistent

## Current Code Touchpoints

- `metta/rl/training/core.py`
- `metta/rl/training/training_environment.py`
- `packages/mettagrid/python/src/mettagrid/envs/mettagrid_puffer_env.py`
- `packages/mettagrid/python/src/mettagrid/policy/policy_env_interface.py`
- `agent/src/metta/agent/components/actor.py`
- `metta/rl/loss/losses.py`
- `recipes/experiment/cogsguard.py`

The important observation is that task and vibe action transport already exists, and the baseline General Agent Substrate plan should keep
vibe action to vibe observation handling inside the existing env or recipe path. The baseline should not introduce a
new substrate-side `vibe_obs` adapter or early communication-cost shaping.

## Target Runtime Contract

At the TensorDict boundary, the baseline General Agent Substrate path should standardize on the keys already needed by the current
environment and trainer:

- environment observation keys already emitted by the env wrapper
- `actions`: task action ids
- `vibe_actions`: vibe action ids
- `rewards`: environment reward consumed by PPO and value learning
- done or truncation flags needed for recurrent-state resets

Optional debug keys worth keeping in replay for analysis:

- `prev_vibe_actions`
- `joint_vibe_actions`
- any env-provided vibe-related observation slice, if it already exists

## Design Direction

### Reuse split action transport

The existing environment wrapper already knows how to ship a primary action plus an optional vibe action. General Agent Substrate should
reuse this immediately.

### Keep vibe observation dynamics in the environment

The substrate definition says `o_{t+1,vibe} = Omega(v_t^{1:N})`, but the implementation plan should treat that as an
existing env responsibility, not a new General Agent Substrate wrapper responsibility. General Agent Substrate should consume whatever the env already emits on
the next step rather than synthesizing a second social-observation view in trainer code.

### Keep discrete vibe actions for phase 1

The current environment uses discrete `change_vibe_*` actions. That is sufficient for the initial General Agent Substrate baseline. The plan
should not assume a continuous communication vector until the environment can actually transport one.

Communication-cost terms and any intrinsic reward coupled to vibe activity are explicitly deferred until the baseline
substrate, routing, and SF path are stable.

## Work Breakdown

### 1. Define AgentSubstrate environment-facing config

Add an `AgentSubstrate` config block, likely under a new module shared by recipes and the new policy, with fields for:

- which existing observation keys the AgentSubstrate policy consumes
- whether AgentSubstrate expects the env wrapper to expose any dedicated vibe-related observation slice
- any env-specific assumptions needed by the recipe and policy interface

Acceptance:

- config validates from recipe payloads
- config serializes through `PolicyArchitecture.to_spec()` when attached to the `AgentSubstrate` policy

### 2. Thread the existing observation bundle into AgentSubstrate policy inputs and replay

The `AgentSubstrate` policy path should consume the current env observation bundle directly. If the env already exposes
a dedicated vibe-related tensor, AgentSubstrate can read it, but the baseline should not require synthesizing one.

Likely touchpoints:

- AgentSubstrate policy experience specs
- rollout key declarations
- replay schemas for any env-provided observation keys the AgentSubstrate policy needs

Acceptance:

- the new AgentSubstrate policy can run rollout and training without synthesizing new observation fields
- replay stores the env-provided observation keys required by AgentSubstrate minibatch training

### 3. Align evaluation and inference paths

The same observation and action contracts must hold outside the training loop.

Work:

- add an AgentSubstrate-aware eval/play path or adapter around stateful policies
- ensure no extra substrate-side vibe-state buffer is required across `Policy.step_with_state()` calls
- define the exact behavior when envs expose or do not expose dedicated vibe-related observation fields

Acceptance:

- a smoke eval path can run an AgentSubstrate checkpoint without any additional vibe-observation adapter state

### 4. Defer reward shaping and intrinsic reward plumbing

The baseline General Agent Substrate path should continue to use the ordinary environment reward in `td["rewards"]`.

If intrinsic reward is added later, it should be introduced as a rollout postprocess step after the SF branch is
working and after the env-facing observation contract is already stable.

Acceptance:

- no new reward decomposition keys are required for the baseline recipe
- later intrinsic reward work has a clean insertion point without revisiting env transport

### 5. Add tests and instrumentation

Required tests:

- AgentSubstrate rollout and eval reuse the current split action transport without missing keys
- any env-provided vibe-related observation slice reaches the AgentSubstrate policy unchanged
- non-AgentSubstrate recipes remain unaffected when the new adapter code is present

Useful metrics:

- fraction of non-default vibe actions
- ordinary environment reward
- any env-provided vibe-observation diagnostics already available in the recipe

## Recommended File Adds

- `tests/rl/test_agent_substrate_env_contract.py`

## Open Questions

1. Which exact env observation keys should the AgentSubstrate policy treat as its baseline input bundle in CogsGuard recipes?
2. If later intrinsic reward work needs a more explicit vibe signal than the current observation stream provides, do we
   add a dedicated replay key then or read it through the policy feature extractor only?
