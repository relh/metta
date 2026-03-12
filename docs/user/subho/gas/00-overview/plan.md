# General Agent Substrate Plan

## Goal

Ship the General Agent Substrate as a new experimental policy and training path without destabilizing the
existing PPO + Cortex recipes.

In docs and design discussion, use `General Agent Substrate` as the formal name. In code, configs, modules, and
TensorDict keys, use `AgentSubstrate` as the short API name.

Formal reference:
- [formalization.md](../formalization.md)

Implementation note:
- the plan files stage baseline subsets of the full formalization; see the formalization document for the full target
  architecture and objective set

Math contract:
- [formalization.md](../formalization.md) is the normative reference for the model equations
- any baseline simplification below is an implementation staging choice, not a redefinition of the formal math

The shortest credible path is:

1. keep existing trainer, replay, PPO actor/critic, and split-action transport where they already match the design,
2. put most reusable AgentSubstrate logic in `packages/cortex/src/cortex/` and keep `metta/rl` as thin orchestration,
3. add a new AgentSubstrate policy architecture and component stack instead of mutating `DefaultPolicyConfig` in place,
4. stage optional pieces behind explicit config flags,
5. land the local inter-layer fabric only after the direct-stride baseline is working and profiled.

## Current Starting Point

The repo already has several pieces we should reuse instead of rebuilding:

- recurrent policy components and checkpointable carry state in `agent/src/metta/agent/components/cortex.py`
- configurable Cortex stacks, cells, blocks, routed adapters, and sequence kernels in `packages/cortex/src/cortex/`
- split primary/vibe action transport in `metta/rl/training/core.py`, `metta/rl/training/training_environment.py`, and
  `packages/mettagrid/python/src/mettagrid/envs/mettagrid_puffer_env.py`
- separate PPO task/vibe actor losses in `metta/rl/loss/ppo_actor.py` and `metta/rl/loss/losses.py`
- a GTD-style successor-feature loss foundation in `metta/rl/loss/diff_horde.py` and
  `packages/cortex/src/cortex/rl/diff_horde.py`
- existing auxiliary-loss patterns for world-model-style training in `metta/rl/loss/cmpo.py`,
  `metta/rl/loss/future_attribute_prediction.py`, and `agent/src/metta/agent/components/drama/`
- trajectory slicing and per-agent route ids in `metta/rl/training/trajectory_isolation.py`
- a routed-selector interface pattern already proven in `packages/cortex/src/cortex/routed_adapter.py`

The main missing pieces are first-class multiscale execution, an explicit RL/WM/SF route split,
objective-conditioned cell selection, and the optional fabric runtime. Vibe action to vibe observation handling should
remain an environment concern for the baseline General Agent Substrate path.

## Subsystem Map

The clean top-level breakdown is:

1. `Sensorimotor Interface`
   - env observations in
   - task and vibe actions out
   - env-side vibe observation effects
   - replay-facing observation and action contract
2. `Multiscale Cortex Core`
   - internal thinking steps `K`
   - layer schedules `p_l`
   - shared lower substrate
   - objective-routed upper routes
   - optional fabric backend
3. `Route Heads`
   - `Decision / Evaluation`: task policy, vibe policy, value
   - `Predictive Modeling`: WM route and world-model targets
   - `Predictive Abstraction`: SF route, `phi`, `psi`, reward abstraction heads
4. `Exploration and Learning`
   - PPO and actor-critic training
   - WM loss
   - SF and GTD update
   - intrinsic reward
   - optional consistency regularization
   - route-enable flags and sweep control

`Local fabric` is not a fifth top-level subsystem. It is an optional backend inside the `Multiscale Cortex Core`.

## Workstream Map

| Spec area | Plan file | Main repo touchpoints |
| --- | --- | --- |
| Overall sequencing and acceptance gates | [this file](./plan.md) | `agent/`, `metta/rl/`, `packages/cortex/`, `packages/mettagrid/` |
| Detailed mathematical formalization | [formalization.md](../formalization.md) | conceptual reference for every subsystem |
| `Sensorimotor Interface` | [10-environment-and-observation-contracts](../10-environment-and-observation-contracts/plan.md) | `metta/rl/training/core.py`, `metta/rl/training/training_environment.py`, `packages/mettagrid/python/src/mettagrid/envs/mettagrid_puffer_env.py`, `packages/mettagrid/python/src/mettagrid/policy/policy_env_interface.py`, `recipes/experiment/cogsguard.py` |
| `Multiscale Cortex Core` | [20-multiscale-cortex-and-routing](../20-multiscale-cortex-and-routing/plan.md) | `agent/src/metta/agent/policies/default.py`, `agent/src/metta/agent/components/cortex.py`, `packages/cortex/src/cortex/` |
| `Route Heads` | [30-auxiliary-routes-and-objectives](../30-auxiliary-routes-and-objectives/plan.md) | `metta/rl/loss/*.py`, `agent/src/metta/agent/components/actor.py`, `agent/src/metta/agent/components/drama/` |
| `Exploration and Learning` | [40-rollout-training-and-validation](../40-rollout-training-and-validation/plan.md) | `metta/rl/trainer.py`, `metta/rl/training/core.py`, `metta/rl/training/experience.py`, `recipes/experiment/` |
| `Multiscale Cortex Core` backend: optional local fabric | [50-local-fabric](../50-local-fabric/plan.md) | `packages/cortex/src/cortex/blocks/column/`, `packages/cortex/src/cortex/stacks/`, `agent/src/metta/agent/components/` |

## Recommended Delivery Order

### Phase 0: Contracts and skeleton

- Add a new `AgentSubstratePolicyConfig` and recipe family instead of threading AgentSubstrate flags through `DefaultPolicyConfig`.
- Define AgentSubstrate config objects for schedule periods, route split, WM/SF heads, route-enable flags, and
  optional fabric selection.
- Decide the objective-id mapping used by routed cell selection:
  - coarse route ids by default: `RL`, `WM`, `SF`
  - optional finer loss ids later, only where there is a real need
- Decide the exact replay/TD keys that will become stable across rollout and training.

### Phase 1: Environment-boundary reuse

- Reuse the current split task/vibe action transport.
- Assume `vibe_actions[t] -> observations[t+1]` stays handled inside the existing environment and recipe path.
- Keep PPO consuming the ordinary environment reward in `td["rewards"]` for the baseline.

### Phase 2: Integrated AgentSubstrate baseline

- Implement the sequence-operator version of the shared lower cortex plus RL/WM/SF upper routes.
- Reuse the existing RL task/vibe/value head machinery off the RL route.
- Add WM prediction loss and SF heads with a GTD-style updater in the same milestone.
- Keep the direct-stride transfer formulation as the only supported execution path at first.
- Expose route outputs and per-layer retained sequences needed by the losses.
- Gate WM and SF routes or losses behind explicit config flags so we can sweep:
  - `RL` only
  - `RL + WM`
  - `RL + SF`
  - `RL + WM + SF`

### Phase 3: Intrinsic reward and optional regularization

- Keep intrinsic reward shaping out of the first end-to-end baseline, but add it only after the SF path is stable.
- Keep route-consistency regularization optional and disabled by default.

### Phase 4: Training-path packing, validation, and performance work

- Make the new component work in rollout and in packed PPO minibatches.
- Add recipe, serialization, smoke tests, and throughput checks.
- Only after the baseline is stable should we decide whether deeper kernel work is necessary.

### Phase 5: Optional local fabric

- Treat the fabric as a separate execution backend, not a small tweak to the direct-stride baseline.
- Land it behind an explicit config switch and only after parity tests exist for the baseline.

## Core Design Decisions

### 1. New architecture, not incremental patching of the default policy

The General Agent Substrate spec changes the execution model enough that adding a pile of optional branches to
`agent/src/metta/agent/policies/default.py` would make the default policy harder to reason about. Create a dedicated
policy config and component path for `AgentSubstrate`.

### 2. Cortex owns reusable AgentSubstrate math and RL primitives

The user wants most of the loss implementation and core functional or RL logic to exist inside Cortex. The plan should
follow that explicitly:

- reusable sequence ops, routing utilities, TD or GTD math, intrinsic-reward math, and objective-routing helpers go in
  `packages/cortex/src/cortex/`
- `metta/rl` keeps trainer integration, replay wiring, metrics, and `LossConfig` registration shells
- AgentSubstrate-specific policy components can live in `agent/`, but the reusable compute they call should prefer Cortex modules

This keeps the architecture library and the RL math library in one reusable place instead of scattering them across
Metta-only loss files.

### 3. Mirror the RoutedAdapter interface for AgentSubstrate cell selection

Current `RoutedAdapter` already has the right operational shape: a per-batch selector id, validated against a fixed slot
count, threaded through the forward path. AgentSubstrate should reuse that interface pattern for routed cell selection.

The important distinction is semantic:

- existing `cortex_route_ids` select adapter slots inside today's Cortex stack
- AgentSubstrate objective ids should select routed cells or routed experts in the AgentSubstrate substrate

So the plan is to mirror the interface, not to silently overload the existing adapter path.

### 4. Reuse current split action transport and env-side vibe handling

The environment stack already supports `actions` and `vibe_actions`. AgentSubstrate should reuse that transport and assume the
existing env or recipe path already turns vibe actions into whatever next-step observation effects are needed. Do not
add a substrate-side `vibe_obs` adapter in the baseline.

### 5. Defer AgentSubstrate-specific reward shaping until later

The trainer already allows rollout postprocessors to mutate rewards before advantage computation. That is the right
place to add intrinsic reward later, but it should not block the baseline multiscale or routed-substrate work.

### 6. Make WM and SF additions sweepable

Backbone, WM, and SF should land in one implementation step, but they should not be hard-wired into one always-on
configuration. The config should support enabling or disabling routed branches and their associated losses so recipe
and ablation sweeps can compare:

- routed RL only
- routed RL with WM
- routed RL with SF
- routed RL with both WM and SF

### 7. Fabric is a second backend

The optional local fabric replaces the direct layer-to-layer transfer rules. That is large enough to deserve its own
backend, configs, tests, and perf gates.

## Acceptance Gates

The baseline General Agent Substrate implementation is complete when all of the following are true:

- there is a dedicated experimental recipe that trains with AgentSubstrate enabled on a local smoke run
- rollout and training both carry AgentSubstrate recurrent state correctly across environment time
- task and vibe actions are emitted from the RL route, while vibe observation effects remain owned by the environment
- the first WM implementation covers the `CMPO`-style next-state and reward slice of Section 8, with the full
  formal world-model target still defined by [formalization.md](../formalization.md)
- the SF route has dedicated heads and a GTD-style update path
- WM and SF branches or losses can be toggled independently for sweep experiments
- routed cell selection is driven by explicit objective ids, with at least the coarse `RL/WM/SF` mapping covered
- packed training and explicit-step execution agree on small parity tests
- checkpoint serialization round-trips for the new policy config and recurrent state
- perf is measured relative to a direct non-AgentSubstrate baseline before optional fabric work starts

## Open Questions To Resolve Early

1. Should the WM branch predict the next routed latent directly, or a projected latent reserved for the `CMPO`-style
   next-state loss?
2. Is the SF branch best implemented as a new AgentSubstrate-specific loss, or by extending `DiffHordeLoss` to read AgentSubstrate keys?
3. Should objective-conditioned routing use only coarse route ids (`RL/WM/SF`) at first, or do we want separate
   selectors for individual losses like `ppo_actor`, `ppo_critic`, `agent_substrate_world_model`, and `agent_substrate_successor_features`?
4. Do we want fixed `K` and `p_l` per recipe only, or per-layer schedules that can vary across policy assets in the
   same run?
5. When intrinsic reward is introduced later, should it be driven purely by SF change, or should it read a more direct
   vibe-conditioned signal from the env observation stream?
