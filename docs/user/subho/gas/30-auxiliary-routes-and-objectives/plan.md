# Auxiliary Routes And Objectives

## Scope

Subsystem: `Route Heads`

Formal reference:
- [formalization.md](../formalization.md)
- especially Sections 5, 8, 9, 10, 11, 12, and 14

Planning note:
- this workstream translates the full RL, WM, and SF route formalization into flag-gated implementation milestones
  that can be swept independently
- Section 8 remains the normative WM target; the `CMPO`-style state-plus-reward loss below is the first
  implementation slice of that route, not a rewrite of the formalization

This workstream covers everything above the substrate execution core:

- RL readouts for task action, vibe action, and value
- WM route predictions and loss
- SF route heads and GTD-style update
- later-stage intrinsic reward from successor or vibe-related change
- total scalar objective assembly
- optional route-consistency regularization

## Current Code Touchpoints

- `agent/src/metta/agent/components/actor.py`
- `metta/rl/loss/ppo_actor.py`
- `metta/rl/loss/ppo_critic.py`
- `metta/rl/loss/diff_horde.py`
- `metta/rl/diff_horde/cumulants.py`
- `metta/rl/loss/future_attribute_prediction.py`
- `metta/rl/loss/cmpo.py`
- `metta/rl/loss/loss.py`
- `metta/rl/training/scheduler.py`
- `agent/src/metta/agent/components/drama/world_model_component.py`
- `metta/rl/loss/losses.py`

The repo already has strong building blocks: dual PPO actor support, a PPO critic, GTD-style diff-horde math, and
examples of stateful auxiliary losses. AgentSubstrate should reuse those patterns wherever the math lines up.

The relevant new preference is that routing should be objective-conditioned using something like a routed-adapter
interface. The existing loss stack already knows the active loss instance and current trajectory slice, so this
workstream should define how those names map onto AgentSubstrate objective ids.

It should also honor the user's architectural preference: most reusable loss math and core RL logic should live inside
`packages/cortex/src/cortex/rl/`, with `metta/rl/loss/` providing thin config and trainer-integration wrappers.

The backbone, RL-head reuse, WM route, and SF route should land as one implementation step rather than as separate
milestones. WM and SF additions should therefore be explicitly flag-gated so one code path can support ablations and
sweeps across route combinations.

## Policy Output Contract

The `AgentSubstrate` policy should expose at least these outputs:

- RL route:
  - `logits`
  - `vibe_logits`
  - `values`
  - optional `h_values` if PPO critic continues to use the existing GTD-lambda path
- WM route:
  - `agent_substrate_wm_state`
  - `agent_substrate_wm_next_state_pred`
  - `agent_substrate_wm_reward_pred`
  - deferred formal target: `agent_substrate_wm_next_vibe_obs_pred`
- SF route:
  - `agent_substrate_sf_state`
  - `agent_substrate_sf_phi`
  - `agent_substrate_sf_psi`
  - `agent_substrate_sf_h` or the equivalent auxiliary GTD head
  - `agent_substrate_sf_reward_pred`
- Split-boundary tensors for optional consistency regularization:
  - `agent_substrate_route_boundary_rl`
  - `agent_substrate_route_boundary_wm`
  - `agent_substrate_route_boundary_sf`

## Work Breakdown

### 1. Define the loss-name to objective-id mapping

Add one explicit mapping layer from training semantics to AgentSubstrate routing semantics.

Recommended baseline:

- `ppo_actor`, `ppo_vibe_actor`, `ppo_critic` -> `RL`
- `agent_substrate_world_model` -> `WM`
- `agent_substrate_successor_features` -> `SF`
- consistency and reward-shaping utilities do not get their own routed cells; they read from the route family they are
  supervising

Implementation options:

- config map from `loss_instance_name` to objective name
- helper on the `AgentSubstrate` policy or AgentSubstrate losses that resolves the active objective slot id
- a small context manager similar to `use_route_ids(...)` when a forward pass needs an explicit selector

Acceptance:

- every AgentSubstrate loss can resolve a stable objective id without ambiguity

Each loss should also respect route-enable flags so:

- WM losses are skipped when the WM route is disabled
- SF losses are skipped when the SF route is disabled

### 2. Move reusable AgentSubstrate loss math into Cortex first

Before adding trainer-facing losses, add reusable functional modules under Cortex for:

- WM target construction helpers for the `CMPO`-style next-state plus reward contract
- successor-feature update math and utilities
- route-consistency penalty math
- any selector-aware helper that needs objective ids

Recommended files:

- `packages/cortex/src/cortex/rl/agent_substrate_world_model.py`
- `packages/cortex/src/cortex/rl/agent_substrate_successor_features.py`
- `packages/cortex/src/cortex/rl/agent_substrate_consistency.py`

Then keep `metta/rl/loss/agent_substrate_*.py` as thin wrappers that:

- declare replay keys
- call the Cortex functions
- register metrics
- integrate with trainer state where necessary

Acceptance:

- the key AgentSubstrate objective math is importable and testable without `metta/rl`

### 3. Wire RL heads off the RL route only

Task action, vibe action, and value should all be driven from the RL route's top-layer state.

The current `ActionProbs` component and PPO vibe actor support should be reused. The main change is that the actor/value
heads read from `agent_substrate_rl_state` instead of a single shared `core` tensor.

Acceptance:

- existing PPO actor and critic losses can consume General Agent Substrate outputs with minimal or no changes
- task and vibe entropies remain separately configurable
- RL-head reuse works in the same build that also enables WM and SF routes

### 4. Add a dedicated General Agent Substrate world-model loss

Implement a new WM auxiliary loss that reads the WM route and predicts:

- next WM state
- immediate reward

This should follow the closest existing repo pattern, which is the `CMPO` world-model loss in
`metta/rl/loss/cmpo.py`: action-conditioned one-step prediction of next state and reward.

The full formal target in Section 8 also includes next vibe observation prediction. The first implementation is
intentionally narrower; if that piece stays deferred, the docs should continue to call this a baseline subset rather
than the complete formal WM route.

Target construction should use time-shifted tensors from the same minibatch sequence, masked across done and truncation
boundaries.

The first version should keep the WM optimizer inside the ordinary scalar objective unless profiling proves it needs a
separate optimizer path.

This loss should be config-gated so it can be enabled or disabled without changing the backbone implementation.

Likely file adds:

- `packages/cortex/src/cortex/rl/agent_substrate_world_model.py`
- `metta/rl/loss/agent_substrate_world_model.py`

Acceptance:

- the loss computes masked next-step targets correctly
- metrics expose state prediction error and reward prediction error separately
- disabling the WM route or WM loss removes its contribution cleanly from the scalar objective

### 5. Add dedicated SF heads and updater

The SF route should no longer be an accident of the critic trunk. It needs explicit `phi` and `psi` heads and a linear
reward head.

Recommended implementation path:

- reuse `packages/cortex/src/cortex/rl/diff_horde.py` for the TD/GTD math
- add an AgentSubstrate-specific wrapper loss that reads AgentSubstrate policy keys and owns any extra state needed for the SF branch
- only extend `DiffHordeLoss` directly if that reduces duplication without making the current diff-horde path harder to
  read

This path should also be config-gated so SF can be swept independently of WM.

Acceptance:

- SF branch has dedicated outputs and does not share upper-route parameters with RL or WM
- reward reconstruction and GTD updates both run from SF outputs
- disabling the SF route or SF loss removes its contribution cleanly from the scalar objective and updater path

### 6. Defer intrinsic reward shaping until the baseline is stable

The spec's intrinsic reward remains useful, but it should not be part of the first end-to-end AgentSubstrate landing.

Prerequisites before adding it:

- direct-stride AgentSubstrate backbone is training end to end
- SF heads and updater are stable
- we know whether the reward should be driven by SF-state change alone or by a more explicit vibe-conditioned signal

When it is added, it should live in Cortex-owned helper code plus a thin rollout postprocess wrapper in `metta/rl`.

### 7. Assemble the scalar objective

The ordinary optimizer should consume a scalar objective composed from:

- RL losses
- WM loss with coefficient `lambda_wm`
- SF reward reconstruction loss with coefficient `lambda_sfr`
- optional consistency regularizer

The exact set of enabled terms should be driven by flags rather than separate architectures.

The SF GTD-style updater remains coupled but distinct, matching the substrate definition.

This likely means:

- scalar-loss components stay within the existing `LossesConfig` path
- the SF loss owns any secondary stateful update it needs, following the same style used by other custom losses

Acceptance:

- ordinary gradient updates and SF auxiliary updates happen in a deterministic, documented order

### 8. Add route-consistency regularization as an opt-in loss

Implement a small AgentSubstrate-specific loss that compares the first routed-layer WM and SF representations against the RL routed
boundary with stop-gradient on the RL side.

This should be disabled by default and only enabled through explicit config.

Acceptance:

- regularizer can be toggled on without changing the policy architecture

### 9. Add tests and metrics

Required tests:

- loss-name-to-objective-id mapping matches config and defaults
- Cortex functional AgentSubstrate math passes unit tests independently of `metta/rl`
- RL heads read from `agent_substrate_rl_state` only
- WM loss target shifting and masking are correct
- SF loss reads `phi`, `psi`, and `psi_next` correctly
- WM and SF flags correctly include or exclude their route outputs and losses
- total scalar objective includes exactly the enabled terms
- consistency loss uses stop-gradient on the RL branch

Useful metrics:

- `wm_state_mse`
- `wm_reward_loss`
- `sf_reward_mse`
- `sf_delta_norm`
- `route_consistency_loss`

## Recommended File Adds

- `packages/cortex/src/cortex/rl/agent_substrate_world_model.py`
- `packages/cortex/src/cortex/rl/agent_substrate_successor_features.py`
- `packages/cortex/src/cortex/rl/agent_substrate_consistency.py`
- `metta/rl/loss/agent_substrate_world_model.py`
- `metta/rl/loss/agent_substrate_successor_features.py`
- `metta/rl/loss/agent_substrate_consistency.py`
- `tests/rl/test_agent_substrate_world_model_loss.py`
- `tests/rl/test_agent_substrate_successor_feature_loss.py`

## Open Questions

1. Should the WM branch predict the next routed latent directly, or a projected latent reserved for the `CMPO`-style
   next-state loss?
2. Should the SF reward head use the same `phi` vector used by GTD, or a lightly projected version to decouple reward
   fitting from successor dynamics?
3. Should the baseline objective-routing mapping stay coarse at `RL/WM/SF`, or do we want distinct slots for losses
   like `ppo_actor` and `ppo_critic`?
4. When intrinsic reward is added later, does it use detached `psi` targets, and does it rewrite `td["rewards"]` or
   stay observable as a separate metric first?
