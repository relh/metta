# RL Experimentation Guide

Guide for coding agents making changes to RL algorithms, agent architectures, losses, or training configs. Read this
before touching anything in `metta/rl/`, `agent/src/metta/agent/`, `packages/cortex/`, or `recipes/`.

## Core Principle

This codebase has a **generalized RL harness** designed so you can try almost anything by adding new files -- new
losses, new policy configs, new components, new recipes -- without modifying the orchestration code. If you feel the
need to change the harness itself, **stop and talk to the user**. The harness is load-bearing infrastructure; changing
it to support one experiment breaks invariants that other experiments rely on.

## Architecture Overview

The training loop has a clear layered design. Understand it before you touch anything:

```
Recipe (recipes/)
  -> TrainTool (metta/tools/train.py)
    -> Trainer (metta/rl/trainer.py)
      -> CoreTrainingLoop (metta/rl/training/core.py)
        -> TrajectoryIsolator slices batches
        -> Losses compute gradients
        -> Policy does forward passes
```

Each layer has a distinct responsibility:

| Layer                        | What it does                                                         | Touch it?                                           |
| ---------------------------- | -------------------------------------------------------------------- | --------------------------------------------------- |
| `TrainTool`                  | Assembles configs, loads policies, registers components              | **No**                                              |
| `Trainer`                    | Creates optimizer, experience buffer, wraps DDP, runs epoch loop     | **No**                                              |
| `CoreTrainingLoop`           | Rollout phase, advantage computation, training phase, gradient steps | **No**                                              |
| `TrajectoryIsolator`         | Splits batches by policy/loss, routes inference                      | **No**                                              |
| `Loss` (base class)          | Hook protocol, state management, scheduling gates                    | **No**                                              |
| `LossesConfig`               | Aggregates loss configs, defines execution order                     | **No**                                              |
| `Policy` (base class)        | Abstract interface for all policies                                  | **No**                                              |
| `PolicyAutoBuilder`          | Builds policies from component lists                                 | **No**                                              |
| Cortex (cells/blocks/stacks) | Memory unit library                                                  | **Rarely** (add new cells, don't change interfaces) |

**Where you should be working:**

| What                     | Where                                                                     | What you do                                        |
| ------------------------ | ------------------------------------------------------------------------- | -------------------------------------------------- |
| New loss functions       | `metta/rl/loss/`                                                          | Add a new file with `LossConfig` + `Loss` subclass |
| New policy architectures | `agent/src/metta/agent/policies/`                                         | Add a new `PolicyArchitecture` config              |
| New components           | `agent/src/metta/agent/components/`                                       | Add a new `ComponentConfig` + `nn.Module`          |
| New cortex cells/blocks  | `packages/cortex/src/cortex/cells/`, `packages/cortex/src/cortex/blocks/` | Register via `@register_cell` / `@register_block`  |
| New recipes              | `recipes/experiment/`                                                     | Python module returning tool instances             |
| Config tweaks            | Recipe files or CLI overrides                                             | Modify hyperparameters                             |

## How to Add a New Loss

This is the most common experiment type. A loss is a pair: a Pydantic config and a dataclass.

### Execution order matters

`LossesConfig` runs losses in **insertion order**. This is critical because losses can communicate through
`shared_loss_data`. The default config runs `ppo_critic` before `ppo_actor` because the critic sets `"advantages_pg"` in
the shared data, which the actor reads. If you add a loss that depends on data set by another loss, ensure the
dependency runs first. If you add a loss that is independent, order doesn't matter, but convention is to place
value/critic losses before policy/actor losses.

### 1. Create your config

```python
# metta/rl/loss/my_loss.py
from pydantic import Field
from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.policy_assets import PolicyAssetRegistry
from metta.rl.training import ComponentContext, TrainingEnvironment

class MyLossConfig(LossConfig):
    my_coef: float = Field(default=0.01, ge=0)
    # ... your hyperparameters

    def create(self, policy_assets, trainer_cfg, env, device, instance_name):
        return MyLoss(policy_assets, trainer_cfg, env, device, instance_name, self)
```

The `create()` signature is fixed. Always pass all six positional args to the `Loss` constructor.

### 2. Implement the loss

```python
class MyLoss(Loss):
    cfg: MyLossConfig
    __slots__ = ()  # See note on __slots__ below

    def get_experience_spec(self) -> Composite:
        """Declare extra fields you need in the replay buffer."""
        return Composite()  # Empty if you don't need anything beyond the defaults

    def policy_output_keys(self, policy_td=None) -> set[str]:
        """Declare which policy output keys your loss uses.
        See the DDP warning below -- getting this wrong causes cryptic crashes."""
        return {"values"}

    def run_train(self, shared_loss_data, context, mb_idx):
        """Your training logic. Returns (loss_tensor, shared_loss_data, stop_epoch)."""
        minibatch = shared_loss_data["sampled_mb"]
        policy_td = shared_loss_data["policy_td"]

        # Your loss computation here
        loss = ...

        self.loss_tracker["my_metric"].append(float(loss.item()))
        return loss, shared_loss_data, False
```

### `policy_output_keys` and DDP

This method tells the harness which policy output keys your loss actually uses. The harness uses this to add a dummy
loss for any **unused** policy parameters so that DDP doesn't crash with `find_unused_parameters=False`. If you forget
to list a key your loss uses, the harness may zero out its gradient contribution. If you list keys that don't exist,
nothing happens. If you fail to list keys that do exist and other losses don't list them either, you get a cryptic DDP
error about "parameters that didn't receive gradients" with no mention of `policy_output_keys` in the traceback.

**Rule of thumb**: return the set of keys you read from `policy_td` in `run_train`.

### The `__slots__` convention

`Loss` is a `@dataclass(slots=True)`. Subclasses that omit `__slots__` will silently get a `__dict__` and can set
arbitrary attributes -- Python allows this. However, the codebase convention is to declare `__slots__` on every Loss
subclass for two reasons: (1) it documents which instance attributes the loss uses, and (2) it prevents accidental
attribute typos from silently creating new attributes instead of raising `AttributeError`.

```python
class MyLoss(Loss):
    cfg: MyLossConfig
    __slots__ = ("my_thing", "other_thing")

    def __init__(self, policy_assets, trainer_cfg, env, device, instance_name, cfg):
        super().__init__(policy_assets, trainer_cfg, env, device, instance_name, cfg)
        self.my_thing = ...
        self.other_thing = ...
```

If your loss has no extra instance attributes, use `__slots__ = ()`. Follow the convention.

### 3. Wire it into a recipe

```python
from metta.rl.loss.my_loss import MyLossConfig
from metta.rl.loss.losses import LossesConfig

losses = LossesConfig()
losses.add_loss("my_loss", MyLossConfig(my_coef=0.05))
```

Or replace an existing loss:

```python
losses = LossesConfig()
losses.replace_loss("ppo_actor", MyLossConfig())
```

### Key loss hooks

Override only the hooks you need. The base class no-ops the rest:

| Hook                                           | When it runs                                   | Common use                                           |
| ---------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------- |
| `run_train(shared_loss_data, context, mb_idx)` | Each minibatch during training                 | **Required** -- your loss computation                |
| `run_rollout_preprocess(td, context)`          | Each timestep before policy forward in rollout | Inject data into the td before inference             |
| `run_rollout_postprocess(td, context)`         | Each timestep after policy forward in rollout  | Copy teacher outputs, override actions               |
| `on_rollout_start(context)`                    | Start of rollout phase                         | Initialize per-rollout state                         |
| `on_epoch_start(context)`                      | Start of each epoch                            | Reset per-epoch state                                |
| `on_mb_end(context, mb_idx)`                   | After each minibatch                           | Update running statistics                            |
| `on_train_phase_end(context)`                  | After all minibatches in an epoch              | Compute epoch-level stats (e.g., explained variance) |
| `save_loss_states(context)`                    | End of training                                | Persist custom loss state                            |

### The shared_loss_data TensorDict

This is passed through all losses in a minibatch. Key entries:

| Key                           | Type       | Description                                                                                              |
| ----------------------------- | ---------- | -------------------------------------------------------------------------------------------------------- |
| `"sampled_mb"`                | TensorDict | The minibatch (observations, rewards, dones, etc.)                                                       |
| `"policy_td"`                 | TensorDict | Policy forward pass outputs (logits, values, entropy, etc.)                                              |
| `"indices"`                   | Tensor     | Buffer indices for updating the replay                                                                   |
| `"advantages"`                | Tensor     | Per-minibatch advantages from the slice                                                                  |
| `"advantages_full"`           | Tensor     | Full advantage buffer (first minibatch only, via NonTensorData)                                          |
| `"advantages_pg"`             | Tensor     | Policy-gradient advantages (set by PPOCritic; absent until critic runs)                                  |
| `"importance_sampling_ratio"` | Tensor     | Ratio of new/old action probs (set by core.py if `act_log_prob` exists in both sampled_mb and policy_td) |
| `"prio_weights"`              | Tensor     | Prioritized sampling weights (only present if using prioritized sampling)                                |

Note: `"advantages_pg"` and `"prio_weights"` are **conditionally present**. Always check with `.get()` or handle
`KeyError` if you read them.

### Updating the replay buffer

If your loss produces values that need to persist across minibatches:

```python
update_td = TensorDict({"my_value": computed_value.detach()}, batch_size=minibatch.batch_size)
indices = shared_loss_data["indices"]
self.replay.update(indices[:, 0], update_td)
```

### Adding extra policy heads from a loss

If your loss needs a new output head (e.g., a prediction network), you have two options:

**Option A: Add a component to the policy config** (preferred for permanent architecture changes). Add a new `MLPConfig`
or custom component to the policy's `components` list in the architecture config.

**Option B: Create a module inside the loss** (preferred for experimental/auxiliary heads). The contrastive loss does
this with a projection head:

```python
if self.projection_head is None:
    self.projection_head = torch.nn.Linear(input_dim, self.embedding_dim).to(self.device)
embeddings = self.projection_head(embeddings)
```

Note: modules created inside losses are not automatically checkpointed with the policy. Use `register_state_attr()` if
you need to persist them.

### Early stopping within an epoch

Return `True` as the third element of `run_train` to stop the current update epoch:

```python
if self.cfg.target_kl is not None:
    avg_kl = np.mean(self.loss_tracker["approx_kl"])
    if avg_kl > self.cfg.target_kl:
        return loss, shared_loss_data, True  # Stop this epoch
```

## How to Add a New Policy Architecture

A policy architecture is a `PolicyArchitecture` config that defines the component pipeline.

### The component pipeline

`PolicyAutoBuilder` runs components sequentially via TensorDictSequential. Each component reads from an `in_key` and
writes to an `out_key`. The data flows through TensorDict:

```
env_obs -> [ObsShim] -> obs_tokens -> [Encoder] -> encoded -> [CortexTD] -> core
                                                                              |
                                                           +--[ActorMLP]----> logits -> [ActionProbs] -> actions, entropy, log_prob
                                                           +--[CriticMLP]---> values
```

### Creating a new architecture

```python
# agent/src/metta/agent/policies/my_arch.py
from metta.agent.policy import PolicyArchitecture, Policy
from metta.agent.components.component_config import ComponentConfig

class MyArchConfig(PolicyArchitecture):
    class_path: str = "metta.agent.policy_auto_builder.PolicyAutoBuilder"

    # Your architecture parameters
    hidden_dim: int = 128
    num_layers: int = 2

    components: list[ComponentConfig] = []
    action_probs_config: ActionProbsConfig = ActionProbsConfig(in_key="logits")

    def make_policy(self, policy_env_info) -> Policy:
        if self.components:
            return super().make_policy(policy_env_info)

        self.components = [
            # Build your component pipeline here
            ObsShimTokensConfig(...),
            MyEncoderConfig(...),
            CortexTDConfig(...),
            MLPConfig(in_key="core", out_key="logits", ...),
            MLPConfig(in_key="core", out_key="values", ...),
            ActorHeadConfig(...),
        ]
        return super().make_policy(policy_env_info)
```

### Important: the `components` guard

Notice the `if self.components:` check. When a checkpoint is loaded, it restores the exact component list that was used
during training. The guard ensures that a restored checkpoint uses its original shapes, not your current defaults.
**Always include this guard.**

### Custom forward methods

If `PolicyAutoBuilder`'s sequential pipeline doesn't work for your architecture (e.g., you need skip connections,
conditional branches, or multi-pass inference), you can write a custom `Policy` subclass:

```python
class MyCustomPolicy(Policy):
    def __init__(self, policy_env_info, config):
        super().__init__(policy_env_info)
        # Build your custom architecture
        self.encoder = ...
        self.memory = ...

    def forward(self, td, action=None):
        # Your custom forward logic
        ...
        return td
```

Set `class_path` in your config to point at your class instead of `PolicyAutoBuilder`.

## How to Add a New Component

Components are `nn.Module` subclasses with a `ComponentConfig`. The base `ComponentConfig` only requires a `name` field
and the abstract `make_component(env)` method. The `in_key`/`out_key` pattern is a **convention** used by all existing
components (not inherited from the base class), and you should follow it.

```python
# agent/src/metta/agent/components/my_component.py
import torch.nn as nn
from metta.agent.components.component_config import ComponentConfig

class MyComponentConfig(ComponentConfig):
    name: str = "my_component"
    in_key: str = "input"       # Convention: declare in_key/out_key
    out_key: str = "output"
    hidden_size: int = 128

    def make_component(self, env=None):
        return MyComponent(self, env)

class MyComponent(nn.Module):
    def __init__(self, config, env=None):
        super().__init__()
        self.config = config
        self.linear = nn.Linear(config.hidden_size, config.hidden_size)

    def forward(self, td):
        x = td[self.config.in_key]
        td[self.config.out_key] = self.linear(x)
        return td
```

Components can optionally implement:

- `initialize_to_environment(policy_env_info, device)` -- called after policy is moved to device
- `get_agent_experience_spec()` -- declare extra replay buffer fields
- `reset_memory()` -- clear recurrent state

## Cortex: Memory and Recurrence

Cortex provides modular recurrent memory via a four-layer abstraction:

```
CortexStack  (stack of blocks)
  -> Block    (projections + normalization around a cell)
    -> Cell   (the actual recurrence: LSTM, mLSTM, sLSTM, TransformerXL, Axon, etc.)
```

### Using cortex in a policy

The standard integration point is `CortexTDConfig`, which wraps a `CortexStack` as a policy component:

```python
CortexTDConfig(
    in_key="encoded_obs",
    out_key="core",
    d_hidden=128,
    stack_cfg=build_cortex_auto_config(
        d_hidden=128,
        pattern="Ag,A,S",      # Axon-gated, Axon, sLSTM
        num_layers=2,
        post_norm=True,
    ),
)
```

### Pattern DSL

The auto-builder accepts compact token patterns. Tokens can be comma-separated (`"A,M,S"`) or space-separated
(`"A M S"`) or concatenated (`"AMS"`). Available tokens (defined in `packages/cortex/src/cortex/tokens.py`):

| Token | Cell                                    | Block type  |
| ----- | --------------------------------------- | ----------- |
| `A`   | Axon (streaming RTU)                    | PostUpGated |
| `Ag`  | AGaLiTe attention                       | PostUpGated |
| `M`   | mLSTM (matrix LSTM)                     | PreUpGated  |
| `M^`  | mLSTM with Axon-augmented gates and QKV | PreUpGated  |
| `S`   | sLSTM (structured LSTM)                 | PostUpGated |
| `S^`  | sLSTM with Axon-augmented gates         | PostUpGated |
| `X`   | TransformerXL attention                 | PostUpGated |
| `X^`  | TransformerXL with Axon-augmented QKV   | PostUpGated |
| `L`   | LSTM (standard)                         | PassThrough |
| `C`   | CausalConv1d                            | PassThrough |

The `^` suffix enables Axon-augmented gates/projections on the base cell. You can also provide a `custom_map` dict to
define your own tokens.

Example: `"Ag,A,S"` creates a 3-block Column with AGaLiTe, Axon, sLSTM experts.

### Adding a new cortex cell

```python
# packages/cortex/src/cortex/cells/my_cell.py
from cortex import MemoryCell, CellConfig, register_cell

class MyCellConfig(CellConfig):
    cell_type: str = "my_cell"
    # ... your params

@register_cell(MyCellConfig)
class MyCell(MemoryCell):
    def init_state(self, batch, *, device, dtype):
        return TensorDict({"hidden": torch.zeros(batch, self.hidden_size, device=device)})

    def forward(self, x, state, *, resets=None):
        # Your recurrence
        return output, new_state

    def reset_state(self, state, mask):
        return TensorDict({k: v * (~mask).unsqueeze(-1) for k, v in state.items()})
```

The `@register_cell` decorator makes it available to the auto-builder. Similarly use `@register_block` for custom
blocks.

## Trajectory Isolation

Trajectory isolation lets you slice the batch so different agent groups use different policies and/or losses. This is
how multi-policy training, teacher-student setups, and mixed-objective experiments work.

### Key concepts

- **Slice**: A named partition of the batch defined by `env_ratio` (random assignment) or `agent_count` (deterministic
  per-environment assignment)
- Each slice has its own `policies`, `primary_policy`, `losses`, `advantage` config, and `sampling` config
- Slices are defined in `TrajectoryIsolationConfig` inside the recipe

### Example: self-play with two policies

```python
trajectory_isolation = TrajectoryIsolationConfig(
    slices=[
        TrajectoryIsolationSliceConfig(
            name="learner",
            env_ratio=0.5,
            policies=["learner0"],
            losses=["ppo_critic", "ppo_actor"],
        ),
        TrajectoryIsolationSliceConfig(
            name="opponent",
            env_ratio=0.5,
            policies=["opponent0"],
            losses=["ppo_critic", "ppo_actor"],
        ),
    ]
)
```

### Example: mixed objectives (PPO + behavior cloning)

```python
trajectory_isolation = TrajectoryIsolationConfig(
    slices=[
        TrajectoryIsolationSliceConfig(
            name="ppo_slice",
            env_ratio=0.7,
            policies=["learner0"],
            losses=["ppo_critic", "ppo_actor"],
        ),
        TrajectoryIsolationSliceConfig(
            name="bc_slice",
            env_ratio=0.3,
            policies=["learner0"],
            losses=["behavior_cloning"],
        ),
    ]
)
```

### Per-slice advantage configuration

Each slice can override advantage computation:

```python
TrajectoryIsolationSliceConfig(
    name="exploration",
    advantage=AdvantageConfig(gamma=0.99, gae_lambda=0.95),
    ...
)
```

### How advantage works in core.py

This is important context. In `CoreTrainingLoop.training_phase`, at the start of each update epoch:

1. If `"values"` exists in the experience buffer, advantages are computed **per-slice** using each slice's
   `AdvantageConfig` (gamma, gae_lambda, vtrace clips)
2. Reward centering subtracts a per-agent EMA baseline before advantage computation
3. The full advantage tensor is stored as `"advantages_full"` in the buffer
4. Individual losses can override or ignore this (e.g., GRPO computes its own group-based advantages)

If your loss needs a different advantage scheme, you can compute it inside `run_train` using the raw rewards and values
from the minibatch. You don't need to change `core.py`.

## Policy Assets

Policy assets manage multiple policies (trainable and non-trainable):

```python
policy_assets = {
    "learner0": PolicyAssetConfig(
        architecture=ViTDefaultConfig(),
        trainable=True,
        optimizer=OptimizerConfig(learning_rate=3e-4),
    ),
    "teacher": PolicyAssetConfig(
        uri="s3://checkpoints/teacher/latest",
        trainable=False,
    ),
}
```

Key fields:

- `trainable=True`: Gets an optimizer, wrapped in DDP, gradients flow
- `trainable=False`: Frozen, eval mode, no optimizer
- `checkpoint=True` (default for trainable): Saves checkpoints during training
- `architecture`: The `PolicyArchitecture` config
- `optimizer`: Per-policy optimizer config (overrides the global one)

## Scheduling: Phased Training and Hyperparameter Annealing

The scheduler system (`metta/rl/training/scheduler.py`) is a powerful tool for phased training. It provides two
mechanisms: **LossRunGate** (turn losses on/off over time) and **ScheduleRule** (anneal any hyperparameter over time or
derive it from metrics). Wire them into your recipe via `SchedulerConfig` on the `TrainTool`.

```python
from metta.rl.training.scheduler import LossRunGate, ScheduleRule, SchedulerConfig

tt.scheduler = SchedulerConfig(
    run_gates=[...],
    rules=[...],
)
```

The scheduler runs automatically -- it applies gates before each rollout and training phase, and applies rules at every
epoch boundary. Losses don't need any special code to be gated; the base `Loss` class checks `_loss_gate_allows()`
before calling `run_train` or `run_rollout_*`.

### LossRunGate: Turn losses on and off

A `LossRunGate` controls whether a loss runs during a specific phase (`"rollout"` or `"train"`) within a time window.
You typically need **two gates per loss** (one for rollout, one for train) unless you want the loss active in one phase
but not the other.

**Fields:**

- `loss_instance_name`: The key in your `LossesConfig` (e.g., `"kickstarter"`, `"ppo_actor"`)
- `phase`: `"rollout"` or `"train"`
- `begin_at_epoch` / `end_at_epoch`: Epoch-based window (half-open: active when `begin <= epoch < end`)
- `begin_at_step` / `end_at_step`: Step-based window (takes priority over epoch fields if set)
- `cycle_length` / `active_in_cycle`: Cyclic activation pattern

If multiple gates exist for the same (loss, phase), they are OR-combined -- the loss is active if **any** gate says so.
If no gate exists for a loss, it defaults to active.

#### Example: Teacher loss active only for first 100 epochs

```python
run_gates=[
    LossRunGate(loss_instance_name="kickstarter", phase="train",
                begin_at_epoch=0, end_at_epoch=100),
    LossRunGate(loss_instance_name="kickstarter", phase="rollout",
                begin_at_epoch=0, end_at_epoch=100),
]
```

After epoch 100, the kickstarter loss stops running entirely.

#### Example: Delayed loss activation

Start PPO actor training only after epoch 50 (e.g., pretrain critic first):

```python
run_gates=[
    LossRunGate(loss_instance_name="ppo_actor", phase="train",
                begin_at_epoch=50),
    LossRunGate(loss_instance_name="ppo_actor", phase="rollout",
                begin_at_epoch=0),  # Still runs inference from epoch 0
]
```

Omitting `end_at_epoch` means the gate stays active forever after `begin_at_epoch`.

#### Example: Cyclic loss activation

Run an auxiliary loss only on certain epochs within a repeating cycle. For example, activate a contrastive loss every
3rd and 4th epoch in a 5-epoch cycle:

```python
run_gates=[
    LossRunGate(loss_instance_name="contrastive", phase="train",
                cycle_length=5, active_in_cycle=[3, 4]),
    LossRunGate(loss_instance_name="contrastive", phase="rollout",
                cycle_length=5, active_in_cycle=[3, 4]),
]
```

`active_in_cycle` uses 1-indexed positions: `epoch_in_cycle = (epoch % cycle_length) + 1`. So for `cycle_length=5`, the
cycle positions are `[1, 2, 3, 4, 5]`.

#### Example: Combining windows with cycles

Gates compose via OR. You can have a loss that runs for the first 200 epochs AND then cyclically every 10th epoch after
that:

```python
run_gates=[
    LossRunGate(loss_instance_name="my_loss", phase="train",
                begin_at_epoch=0, end_at_epoch=200),
    LossRunGate(loss_instance_name="my_loss", phase="train",
                begin_at_epoch=200,
                cycle_length=10, active_in_cycle=[1]),
]
```

### ScheduleRule: Anneal hyperparameters

A `ScheduleRule` modifies any config value over time. It can operate in two modes:

**Progress mode** (default): Interpolate between `start_value` and `end_value` over an epoch or step range using an
annealing curve.

**Metric mode**: Derive the value from a reported rollout metric with optional EMA smoothing and clamping.

#### target_path syntax

The `target_path` is a dotted path relative to `TrainerConfig` with optional bracket selectors:

- `"losses.ppo_actor.ent_coef"` -- loss config field
- `"losses.ppo_critic.vf_coef"` -- another loss config field
- `"losses.kickstarter.ks_coef"` -- kickstarter coefficient
- `"optimizer.learning_rate"` -- global optimizer learning rate
- `"policy_assets['learner0'].optimizer.learning_rate"` -- per-policy learning rate

The scheduler automatically syncs optimizer learning rates with the config values after applying rules, so annealing
`optimizer.learning_rate` or `policy_assets['learner0'].optimizer.learning_rate` works correctly.

#### Built-in annealing styles

Three curves are available via the `style` field:

- `"linear"`: Straight-line interpolation from `start_value` to `end_value`
- `"cosine"`: Cosine annealing (slow start, fast middle, slow end)
- `"sawtooth"`: Repeating ramp (useful for cyclical schedules -- `progress % 1.0`)

All curves are evaluated as `fn(progress, start_value, end_value)` where `progress` is
`(current - start) / (end - start)`, clamped to `[0, 1]` (except sawtooth which wraps).

#### Example: Linear entropy annealing

Ramp entropy coefficient from 0.02 to 0.001 over the first 500 epochs:

```python
rules=[
    ScheduleRule(
        target_path="losses.ppo_actor.ent_coef",
        start_value=0.02,
        end_value=0.001,
        start_epoch=0,
        end_epoch=500,
        style="linear",
    ),
]
```

#### Example: Cosine learning rate warmup then decay

```python
rules=[
    ScheduleRule(
        target_path="policy_assets['learner0'].optimizer.learning_rate",
        start_value=1e-5,
        end_value=3e-4,
        start_epoch=0,
        end_epoch=50,
        style="cosine",
    ),
    ScheduleRule(
        target_path="policy_assets['learner0'].optimizer.learning_rate",
        start_value=3e-4,
        end_value=1e-5,
        start_epoch=50,
        end_epoch=1000,
        style="cosine",
    ),
]
```

#### Example: Step-based scheduling

Use agent steps instead of epochs for finer-grained control:

```python
ScheduleRule(
    target_path="losses.kickstarter.ks_coef",
    start_value=1.0,
    end_value=0.0,
    start_agent_step=0,
    end_agent_step=50_000_000,
    style="linear",
)
```

When both step and epoch fields are set, **step fields take priority**.

#### Example: Metric-driven scheduling

Derive a hyperparameter from a live rollout metric:

```python
ScheduleRule(
    target_path="losses.ppo_critic.vf_coef",
    mode="metric",
    metric_key="env_game/hub.hearts.created",
    ema_beta=0.9,       # Smooth with exponential moving average
    min_value=0.1,      # Clamp floor
    max_value=1.0,      # Clamp ceiling
)
```

You can also provide a `transform` callable for arbitrary mappings:

```python
ScheduleRule(
    target_path="losses.ppo_actor.ent_coef",
    mode="metric",
    metric_key="overview/approx_kl",
    transform=lambda kl: max(0.001, 0.01 * (1.0 - kl / 0.05)),
    ema_beta=0.8,
)
```

### Putting it all together

A complete phased training recipe with teacher warmup, entropy annealing, and learning rate scheduling:

```python
def train() -> TrainTool:
    losses = LossesConfig()
    losses.add_loss("kickstarter", KickstarterConfig(ks_coef=1.0))

    tt = TrainTool(
        trainer=TrainerConfig(total_timesteps=1_000_000_000),
        training_env=TrainingEnvironmentConfig(curriculum=make_curriculum()),
        losses=losses,
        policy_assets={
            "learner0": PolicyAssetConfig(architecture=ViTDefaultConfig()),
            "teacher": PolicyAssetConfig(uri="s3://checkpoints/teacher", trainable=False),
        },
        scheduler=SchedulerConfig(
            run_gates=[
                # Teacher active for first 200 epochs
                LossRunGate(loss_instance_name="kickstarter", phase="train",
                            begin_at_epoch=0, end_at_epoch=200),
                LossRunGate(loss_instance_name="kickstarter", phase="rollout",
                            begin_at_epoch=0, end_at_epoch=200),
            ],
            rules=[
                # Fade out kickstarter coefficient
                ScheduleRule(
                    target_path="losses.kickstarter.ks_coef",
                    start_value=1.0, end_value=0.0,
                    start_epoch=100, end_epoch=200,
                    style="cosine",
                ),
                # Anneal entropy
                ScheduleRule(
                    target_path="losses.ppo_actor.ent_coef",
                    start_value=0.02, end_value=0.001,
                    start_epoch=0, end_epoch=500,
                    style="linear",
                ),
            ],
        ),
    )
    return tt
```

## Loss State Checkpointing

Losses can persist custom state across restarts using `register_state_attr()`. The base class automatically registers
`loss_tracker`. If your loss has additional state (e.g., EMA targets, running statistics, learned modules):

```python
def __post_init__(self):
    super().__post_init__()
    self.register_state_attr("my_ema_target", "my_running_mean")
```

The registered attributes are saved/restored via `state_dict()` / `load_state_dict()`, which follow `torch.nn.Module`
semantics. Tensors are cloned to CPU on save and restored to the correct device on load.

## Design Sketch: Phasic Policy Gradient (PPG)

This section walks through how you'd implement something like [Phasic Policy Gradient](https://arxiv.org/abs/2009.04416)
using the existing harness. PPG alternates between a standard PPO policy phase and an auxiliary phase that distills
value information into the policy's representation via a separate auxiliary critic head. The auxiliary phase runs every
N epochs on a replay of recent experience, with its own optimizer.

This is a good example of a complex algorithm that fits within the harness without modifying any core files. The key
patterns are:

1. **A loss with its own optimizer** -- the auxiliary head parameters are optimized independently
2. **A loss with its own replay buffer** -- the auxiliary phase trains on stored rollout data
3. **Cyclic scheduling** -- the auxiliary phase fires every N epochs via `LossRunGate`
4. **Custom `state_dict`/`load_state_dict`** -- to checkpoint the auxiliary head and its buffer

For a working example of patterns 1-2 and 4, study `cmpo.py` which builds a world model ensemble with its own optimizer
and transition buffer inside the loss.

### The loss

```python
# metta/rl/loss/ppg_auxiliary.py

class PPGAuxConfig(LossConfig):
    aux_epochs: int = Field(default=6, ge=1)
    aux_lr: float = Field(default=5e-4, gt=0)
    beta_clone: float = Field(default=1.0, ge=0)
    buffer_epochs: int = Field(default=32, ge=1)

    def create(self, policy_assets, trainer_cfg, env, device, instance_name):
        return PPGAuxLoss(policy_assets, trainer_cfg, env, device, instance_name, self)


class PPGAuxLoss(Loss):
    cfg: PPGAuxConfig
    __slots__ = (
        "aux_head", "aux_optimizer", "rollout_buffer",
        "_buffer_count", "_aux_epochs_done",
    )

    def __init__(self, policy_assets, trainer_cfg, env, device, instance_name, cfg):
        super().__init__(policy_assets, trainer_cfg, env, device, instance_name, cfg)

        # Auxiliary value head -- separate from the policy's own critic.
        # Initialized lazily on first use since we don't know the feature dim yet.
        self.aux_head = None
        self.aux_optimizer = None

        # Simple buffer storing recent rollout features + value targets.
        self.rollout_buffer = []
        self._buffer_count = 0
        self._aux_epochs_done = 0

    def get_experience_spec(self) -> Composite:
        return Composite()  # No extra replay fields needed

    def policy_output_keys(self, policy_td=None) -> set[str]:
        # We read the core features and values from the policy
        return {"core", "values"}

    def on_epoch_start(self, context=None):
        """Snapshot rollout features for the auxiliary phase buffer."""
        super().on_epoch_start(context)
        ctx = self._require_context(context)

        # Store a snapshot of the current rollout's features and value targets.
        # In practice you'd read from self.replay.buffer after the rollout.
        if self.replay is not None and "values" in self.replay.buffer.keys():
            features = self.replay.buffer.get("core", None)
            values = self.replay.buffer["values"]
            if features is not None:
                self.rollout_buffer.append({
                    "features": features.detach().clone(),
                    "value_targets": values.detach().clone(),
                    "old_log_probs": self.replay.buffer.get("act_log_prob",
                                     torch.zeros_like(values)).detach().clone(),
                })
                self._buffer_count += 1
                # Keep only the last N epochs of data
                max_keep = self.cfg.buffer_epochs
                if len(self.rollout_buffer) > max_keep:
                    self.rollout_buffer = self.rollout_buffer[-max_keep:]

    def run_train(self, shared_loss_data, context, mb_idx):
        """The auxiliary training phase.

        When the scheduler gates this loss ON (every N epochs), we run
        multiple passes over the buffered rollout data, training:
        1. The auxiliary value head on value targets
        2. A KL penalty to keep the policy close to its pre-auxiliary behavior
        """
        if not self.rollout_buffer:
            return self._zero(), shared_loss_data, False

        policy = self.policy
        policy_td = shared_loss_data["policy_td"]

        # Lazy-init the auxiliary head once we know the feature dimension
        if self.aux_head is None:
            feat_dim = policy_td["core"].shape[-1]
            self.aux_head = torch.nn.Linear(feat_dim, 1).to(self.device)
            self.aux_optimizer = torch.optim.Adam(
                self.aux_head.parameters(), lr=self.cfg.aux_lr
            )

        # Run auxiliary epochs over the buffered data
        if mb_idx == 0:
            self._run_auxiliary_phase(policy)

        # During the normal minibatch pass, just contribute a behavioral cloning
        # penalty to prevent the shared representation from drifting
        old_log_probs = shared_loss_data["sampled_mb"].get("act_log_prob", None)
        new_log_probs = policy_td.get("act_log_prob", None)
        if old_log_probs is not None and new_log_probs is not None:
            kl = (old_log_probs.exp() * (old_log_probs - new_log_probs)).mean()
            loss = self.cfg.beta_clone * kl
            self.loss_tracker["ppg_kl"].append(float(kl.item()))
            return loss, shared_loss_data, False

        return self._zero(), shared_loss_data, False

    def _run_auxiliary_phase(self, policy):
        """Train the auxiliary head on buffered data."""
        for _ in range(self.cfg.aux_epochs):
            for stored in self.rollout_buffer:
                features = stored["features"].to(self.device)
                targets = stored["value_targets"].to(self.device)

                # Forward through auxiliary head
                aux_values = self.aux_head(features).squeeze(-1)
                aux_loss = 0.5 * (aux_values - targets).pow(2).mean()

                self.aux_optimizer.zero_grad()
                aux_loss.backward()
                self.aux_optimizer.step()

                self.loss_tracker["ppg_aux_value_loss"].append(float(aux_loss.item()))

        self._aux_epochs_done += 1

    # Checkpoint the auxiliary head and buffer
    def state_dict(self):
        state = super().state_dict()
        if self.aux_head is not None:
            state["aux_head"] = {k: v.cpu() for k, v in self.aux_head.state_dict().items()}
        if self.aux_optimizer is not None:
            state["aux_optimizer"] = self.aux_optimizer.state_dict()
        state["_aux_epochs_done"] = self._aux_epochs_done
        return state

    def load_state_dict(self, state_dict, *, strict=True):
        missing, unexpected = super().load_state_dict(
            {k: v for k, v in state_dict.items() if k in self._state_attrs},
            strict=False,
        )
        if "aux_head" in state_dict and self.aux_head is not None:
            self.aux_head.load_state_dict(state_dict["aux_head"])
        if "aux_optimizer" in state_dict and self.aux_optimizer is not None:
            self.aux_optimizer.load_state_dict(state_dict["aux_optimizer"])
        self._aux_epochs_done = state_dict.get("_aux_epochs_done", 0)
        return missing, unexpected
```

### The recipe

```python
# recipes/experiment/ppg.py
from metta.rl.loss.ppg_auxiliary import PPGAuxConfig
from metta.rl.training.scheduler import LossRunGate, SchedulerConfig
from recipes.prod.arena_basic_easy_shaped import train as base_train

def train() -> TrainTool:
    tt = base_train()

    # Add the auxiliary loss
    tt.trainer.losses.add_loss("ppg_aux", PPGAuxConfig(
        aux_epochs=6,
        beta_clone=1.0,
        buffer_epochs=32,
    ))

    # Gate it to run every 32nd epoch (the auxiliary phase interval)
    tt.scheduler = SchedulerConfig(
        run_gates=[
            LossRunGate(
                loss_instance_name="ppg_aux",
                phase="train",
                cycle_length=32,
                active_in_cycle=[32],  # Fire on the last epoch of each cycle
            ),
            # Auxiliary loss doesn't need rollout -- it uses buffered data.
            # But on_epoch_start still runs to collect buffer snapshots.
            LossRunGate(
                loss_instance_name="ppg_aux",
                phase="rollout",
                begin_at_epoch=0,  # Always active for rollout (buffer collection)
            ),
        ],
    )
    return tt
```

### Why this works without modifying the harness

- The **auxiliary head** lives inside the loss, not the policy. It has its own `nn.Linear` and its own `Adam` optimizer.
  The policy's optimizer never touches it.
- The **replay buffer** is just a Python list inside the loss. `on_epoch_start` snapshots data from `self.replay.buffer`
  (the shared experience buffer) into the loss's private buffer.
- The **auxiliary training loop** runs inside `run_train` at `mb_idx == 0`, similar to how CMPO trains its world model.
  This means the auxiliary phase happens within the normal training phase call -- no special epoch-level hooks needed.
- The **scheduler** gates the loss so `run_train` is only called every 32nd epoch. On other epochs,
  `_loss_gate_allows("train", ...)` returns `False` and the base class short-circuits. But `on_epoch_start` still runs
  every epoch to collect buffer snapshots (hooks are not gated).
- **Checkpointing** works via custom `state_dict`/`load_state_dict`, following the same pattern as CMPO.

This pattern generalizes to any algorithm that needs periodic auxiliary optimization phases -- BYOL-style
self-supervised losses, world model training, representation distillation, etc.

## Testing Your Changes

### Local smoke test

On macOS, the harness automatically minimizes batch sizes and horizons so you can test locally:

```bash
uv run ./tools/run.py train recipes.experiment.my_experiment run=test_run trainer.total_timesteps=100000
```

### Sandbox mode

For fast validation on GPU (1M steps, checkpoints and evals after epoch 1):

```bash
uv run ./tools/run.py train recipes.experiment.my_experiment run=sandbox_test -- sandbox=True
```

### Running tests

```bash
metta pytest tests/rl/test_losses.py -v          # Loss-specific tests
metta pytest tests/rl/ -v                         # All RL tests
metta pytest --changed                            # Tests affected by your changes
```

If you add a new loss, consider adding a test in `tests/rl/` that validates basic forward/backward behavior. See
`tests/rl/test_losses.py` for patterns.

## Writing a Recipe

Recipes live in `recipes/experiment/` (for experiments) or `recipes/prod/` (CI-validated).

A recipe is a Python module with tool-maker functions:

```python
# recipes/experiment/my_experiment.py
from metta.tools.train import TrainTool
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import TrainingEnvironmentConfig
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.loss.my_loss import MyLossConfig
from metta.rl.loss.losses import LossesConfig

def train() -> TrainTool:
    losses = LossesConfig()
    losses.add_loss("my_loss", MyLossConfig(coef=0.1))

    return TrainTool(
        trainer=TrainerConfig(total_timesteps=100_000_000),
        training_env=TrainingEnvironmentConfig(curriculum=make_curriculum()),
        losses=losses,
        policy_assets={"learner0": PolicyAssetConfig(architecture=MyArchConfig())},
    )
```

Run it: `uv run ./tools/run.py train recipes.experiment.my_experiment`

Recipes can import from other recipes to share configurations:

```python
from recipes.prod.arena_basic_easy_shaped import train as base_train, simulations

def train():
    return base_train(policy_architecture=MyArchConfig())
```

## What NOT To Do

### Do not modify these files for experiments

These files define the training harness. Changing them to accommodate one experiment risks breaking the invariants that
all other experiments depend on:

| File                                           | Why it's fixed                                              |
| ---------------------------------------------- | ----------------------------------------------------------- |
| `metta/tools/train.py`                         | Assembles the full training pipeline from configs           |
| `metta/rl/trainer.py`                          | Manages the epoch loop, optimizer lifecycle, DDP wrapping   |
| `metta/rl/training/core.py`                    | Rollout/train phases, advantage computation, gradient steps |
| `metta/rl/loss/loss.py`                        | Base `Loss` class defining the hook protocol                |
| `metta/rl/loss/losses.py`                      | `LossesConfig` aggregation and execution order              |
| `agent/src/metta/agent/policy.py`              | `Policy` and `PolicyArchitecture` base classes              |
| `agent/src/metta/agent/policy_auto_builder.py` | Sequential component execution                              |
| `metta/rl/training/trajectory_isolation.py`    | Batch slicing and routing                                   |
| `metta/rl/policy_assets.py`                    | Multi-policy registry                                       |
| `metta/rl/training/experience.py`              | Replay buffer structure                                     |

### Do not add try/except

Per codebase policy: let it crash. If your loss receives unexpected data, that's a bug in the setup, not something to
catch and swallow.

### Do not add defensive None checks

If a value should always exist, assert it. Don't guard against hypothetical `None`s. Fix the callsite or the config
instead.

### Do not add backwards compatibility shims

If you change a config field name, update every callsite. Don't add aliases or fallbacks.

## When You Need to Break the Rules

Sometimes an experiment genuinely requires changing the harness. Reasons this might happen:

- The hook protocol doesn't support a lifecycle event you need (e.g., mid-rollout model updates)
- The experience buffer can't represent your data shape
- Trajectory isolation doesn't support your batching scheme
- The advantage computation needs a fundamentally different structure

**If this happens:**

1. **Stop and explain the constraint to the user.** Describe what you're trying to do and why the current harness
   doesn't support it.
2. **Propose the minimal harness change.** Don't redesign the system. Propose an additive change (new hook, new optional
   field) that doesn't break existing behavior.
3. **Get explicit approval** before modifying any file in the "do not modify" list.
4. **Ensure all existing losses and recipes still work** after your change.

## Quick Reference: File Locations

```
metta/rl/loss/              # All loss implementations (add new files here)
metta/rl/loss/loss.py       # Base Loss class (do not modify)
metta/rl/loss/losses.py     # LossesConfig (do not modify)
metta/rl/training/core.py   # CoreTrainingLoop (do not modify)
metta/rl/trainer.py         # Trainer facade (do not modify)
metta/rl/trainer_config.py  # TrainerConfig, OptimizerConfig, etc.
metta/rl/advantage.py       # GAE/vtrace computation
metta/rl/policy_assets.py   # PolicyAssetConfig and registry

agent/src/metta/agent/
  policy.py                 # Policy base class (do not modify)
  policy_auto_builder.py    # Component pipeline builder (do not modify)
  policies/                 # Policy architecture configs (add new files here)
  components/               # Component configs and modules (add new files here)

packages/cortex/src/cortex/
  cells/                    # Memory cells (add new files here)
  blocks/                   # Block wrappers (add new files here)
  stacks/                   # Stack builders
  tokens.py                 # Token registry (register new tokens here)
  config.py                 # Cortex config classes

recipes/
  experiment/               # Experimental recipes (add new files here)
  prod/                     # CI-validated production recipes
```

## Existing Losses Worth Studying

Before writing a new loss, read these to understand the patterns:

| Loss                        | File                             | Notable pattern                                                                              |
| --------------------------- | -------------------------------- | -------------------------------------------------------------------------------------------- |
| PPO Actor                   | `ppo_actor.py`                   | Standard clipped policy gradient, importance sampling, early stopping                        |
| PPO Critic                  | `ppo_critic.py`                  | Value loss, explained variance stats, sets `advantages_pg` for actor                         |
| CMPO                        | `cmpo.py`                        | Model-based: builds world model ensemble inside the loss, custom forward pass, own optimizer |
| Future Attribute Prediction | `future_attribute_prediction.py` | Auxiliary predictive loss, adds prediction head via policy component, masks obs tokens       |
| Contrastive                 | `contrastive.py`                 | Dynamic projection head creation, embedding auto-detection                                   |
| Kickstarter                 | `kickstarter.py`                 | Teacher-student, uses `rollout_postprocess` to copy teacher outputs                          |

## Existing Architectures Worth Studying

| Architecture      | File                   | Notable pattern                                                   |
| ----------------- | ---------------------- | ----------------------------------------------------------------- |
| ViTDefault        | `vit.py`               | Standard: perceiver encoder + Cortex trunk + actor/critic heads   |
| CortexBase        | `cortex.py`            | xLSTM-based memory, overridable stack configuration               |
| ViT Shared Critic | `vit_shared_critic.py` | MAPPO-style shared critic component, multi-agent value estimation |
| ViT GRPO          | `vit_grpo.py`          | No critic network (value-free policy for GRPO)                    |
| ViT Quantile      | `vit_quantile.py`      | Distributional critic with quantile outputs                       |
