# Cortex

`cortex` is a PyTorch library for building recurrent backbones, memory modules, and routed mixtures of stateful experts.
It separates stateful computation from architectural wrapping so you can compose new memory stacks quickly and safely.

At the public API level, Cortex is organized around three concepts:

- `core`: the primitive stateful computation unit
- `scaffold`: the residual/projection/gating wrapper around a core
- `cell`: a programmer-facing pairing of `scaffold + core`

The package is published as `cortexcore` and imported as `cortex`.

## Install

```bash
pip install cortexcore
```

## Table of Contents

- [Install](#install)
- [Architecture](#architecture)
  - [Why This Design](#why-this-design)
  - [Uniform Interface Design](#uniform-interface-design)
- [Quick Start](#quick-start)
  - [Built-In Cells](#built-in-cells)
  - [Global Overrides](#global-overrides)
  - [Routed Adapters](#routed-adapters)
- [Supported Components](#supported-components)
  - [Cells](#cells)
  - [Cores](#cores)
  - [Scaffolds](#scaffolds)
  - [Hidden Size Inference in Scaffolds](#hidden-size-inference-in-scaffolds)
- [Column and MoE Routing](#column-and-moe-routing)
  - [Compact Forward Pass](#compact-forward-pass)
- [Advanced Setup](#advanced-setup)
  - [Manual Stack Construction](#manual-stack-construction)
  - [Manual Column Construction](#manual-column-construction)
  - [Hugging Face LLaMA Integration](#hugging-face-llama-integration)
- [AxonLayer](#axonlayer)
  - [Internal Structure](#internal-structure)
  - [AxonLayer Integration Across Cores](#axonlayer-integration-across-cores)
- [Evaluate Quickly](#evaluate-quickly)
- [Backend Configuration](#backend-configuration)
- [Extending Cortex](#extending-cortex)
  - [Custom Core](#custom-core)
  - [Custom Scaffold](#custom-scaffold)
  - [Custom Cell Presets and Stack Recipes](#custom-cell-presets-and-stack-recipes)
- [Package Layout](#package-layout)

## Architecture

Cortex has five important abstractions:

1. **Core**
   - The runtime stateful unit.
   - Responsible for recurrence, attention-style memory, or temporal state updates.
   - Examples: `LSTMCore`, `mLSTMCore`, `sLSTMCore`, `XLCore`, `AGaLiTeCore`, `AxonCore`.

2. **Scaffold**
   - A wrapper around a core that handles projection, gating, residual structure, normalization, and routing.
   - Examples: `PassThroughScaffold`, `PreUpScaffold`, `PostUpScaffold`, `AdapterScaffold`, `ColumnScaffold`.

3. **Cell**
   - The public config-level unit most users work with.
   - A `CellConfig` bundles a scaffold and a core so you can specify expert sets directly.
   - Examples: `AxonCellConfig()`, `XLCellConfig()`, `mLSTMCellConfig()`.

4. **Column**
   - A routed mixture of expert scaffolds executed in parallel and mixed by a router.
   - Used by the auto builders to form MoE-style memory layers.

5. **Stack**
   - A layered composition where each layer is a Column, and each Column is a mixture of cells.

### Why This Design

Separating cores from scaffolds gives you:

- **Modularity**: swap temporal mechanisms without rewriting projection or residual logic
- **Composability**: reuse the same cores in different scaffold patterns and routed mixtures
- **Clarity**: keep memory computation separate from architectural wrapping
- **Auto-configuration**: infer working dimensions from `d_hidden` instead of manually wiring every hidden size
- **Flexibility**: define explicit cells for programmer-facing recipes while keeping low-level control available
- **Gradient stability**: use skip paths, gating, normalization, and routed mixtures without baking those concerns into the core
- **Performance**: select Triton, CUDA, or PyTorch backends per core as available

### Uniform Interface Design

A core design principle is that **cores, scaffolds, columns, and stacks all share the same runtime interface**. A cell
is a config object, but the modules it expands into follow the same stateful contract:

```python
def forward(
    x: Tensor,
    state: TensorDict | None,
    *,
    resets: ResetMask | None = None,
) -> tuple[Tensor, TensorDict | None]:
    ...
```

- **Input**: `[B, T, H]` for sequence mode or `[B, H]` for step mode
- **State**: always a `TensorDict`, with nesting determined by the current abstraction
- **Output**: same outer shape as input
- **Resets**: optional episode-boundary mask, passed automatically through stacks and scaffolds down into cores

Typical state structure:

- Core state: flat, for example `{"h": ..., "c": ...}`
- Scaffold state: wraps core state under the core module class name, for example `{"LSTMCell": {"h": ..., "c": ...}}`
- Column state: one entry per expert scaffold
- Stack state: one entry per scaffold, indexed by scaffold type and position

This uniformity lets you treat a deep memory stack like any other recurrent module.

## Quick Start

The highest-level builder is `build_cortex_auto_stack`. It creates a stack of Column layers from explicit cell lists.

```python
import torch
from cortex.cells import AxonCellConfig, XLCellConfig, mLSTMCellConfig, sLSTMCellConfig
from cortex.stacks import build_cortex_auto_stack

stack = build_cortex_auto_stack(
    d_hidden=256,
    num_layers=2,
    layers=[
        [AxonCellConfig(), XLCellConfig(), mLSTMCellConfig(), sLSTMCellConfig()],
        [AxonCellConfig(), XLCellConfig(), mLSTMCellConfig(), sLSTMCellConfig()],
    ],
)

x = torch.randn(4, 32, 256)
y, state = stack(x, state=None)
```

Step mode uses `[B, H]` inputs:

```python
x_t = torch.randn(4, 256)
state = stack.init_state(batch=4, device=x_t.device, dtype=x_t.dtype)
y_t, state = stack.step(x_t, state)
```

If `layers` is omitted, the builder repeats `default_cells()` for `num_layers` layers.

### Built-In Cells

Cells are the easiest way to specify the expert set you want. Each built-in cell chooses a default scaffold and core:

| Cell Config | Default Scaffold | Default Core | Notes |
| ----------- | ---------------- | ------------ | ----- |
| `AxonCellConfig()` | `PostUpGatedScaffoldConfig` | `AxonCoreConfig` | Streaming RTU-style memory with stateful linear dynamics |
| `XLCellConfig()` | `PostUpGatedScaffoldConfig` | `XLCoreConfig` | Transformer-XL style memory with rolling cache |
| `mLSTMCellConfig()` | `PreUpGatedScaffoldConfig` | `mLSTMCoreConfig` | Matrix-LSTM with chunked sequence updates |
| `sLSTMCellConfig()` | `PostUpGatedScaffoldConfig` | `sLSTMCoreConfig` | Structured LSTM with stabilized accumulators |
| `LSTMCellConfig()` | `PassThroughScaffoldConfig` | `LSTMCoreConfig` | Plain recurrent baseline |
| `CausalConv1dCellConfig()` | `PassThroughScaffoldConfig` | `CausalConv1dCoreConfig` | Causal convolutional memory core |
| `AGaLiTeCellConfig()` | `PostUpGatedScaffoldConfig` | `AGaLiTeCoreConfig` | Attention-style recurrent discounted state |

You can override the nested core directly:

```python
from cortex.cells import XLCellConfig, mLSTMCellConfig
from cortex.config import XLCoreConfig, mLSTMCoreConfig

layer = [
    XLCellConfig(core=XLCoreConfig(mem_len=256, use_axon_qkv=True)),
    mLSTMCellConfig(core=mLSTMCoreConfig(num_heads=8, chunk_size=32)),
]
```

And you can always construct an explicit cell yourself:

```python
from cortex import CellConfig
from cortex.config import PostUpScaffoldConfig, XLCoreConfig

cell = CellConfig(
    scaffold=PostUpScaffoldConfig(proj_factor=2.0),
    core=XLCoreConfig(mem_len=128),
)
```

### Global Overrides

`override_global_configs` lets you modify every matching config type inside an auto-built stack without rebuilding each
layer manually.

```python
from cortex.cells import XLCellConfig
from cortex.config import RouterConfig, XLCoreConfig
from cortex.stacks import build_cortex_auto_stack

stack = build_cortex_auto_stack(
    d_hidden=256,
    num_layers=3,
    layers=[[XLCellConfig()]] * 3,
    router=RouterConfig(d_key=128, temperature=0.7),
    override_global_configs=[XLCoreConfig(mem_len=512)],
)
```

Notes:

- Overrides apply by model type across the generated config tree.
- Only explicitly set fields are merged.
- Core `hidden_size` is still inferred by the enclosing scaffold/stack where applicable.

### Routed Adapters

Cortex can inject route-ID-aware low-rank adapters into linear-like modules across the stack:

```python
import torch
from cortex import RoutedAdapterConfig
from cortex.cells import AxonCellConfig, XLCellConfig
from cortex.stacks import build_cortex_auto_stack

stack = build_cortex_auto_stack(
    d_hidden=256,
    layers=[[AxonCellConfig(), XLCellConfig()]],
    routed_adapter=RoutedAdapterConfig(num_slots=64, rank=8, dropout=0.0),
)

B, T = 4, 16
x = torch.randn(B, T, 256)
route_ids = torch.tensor([0, 5, 12, 7], dtype=torch.long)
out, state = stack(x, route_ids=route_ids)
```

Notes:

- `route_ids` has shape `[B]`
- sequence inputs `[B, T, H]` reuse the same route per batch row across time
- `compile_blocks` is disabled automatically when routed adapters are enabled
- `set_trunk_lr_mult_(stack, value)` can scale gradients on non-adapter parameters at runtime

Current caveats:

- `LSTMCore` uses `nn.LSTM` weights directly, so routed adapters do not currently affect it
- `CausalConv1dCore` has no linear projections to adapt
- some Axon-backed sequence projections flatten batch and time, so not every linear path can be route-adapted

## Supported Components

### Cells

Public cell configs live in `cortex.cells`. They are the main user-facing selection surface for auto-built stacks and
columns.

The default expert recipe returned by `default_cells()` is:

```python
from cortex.cells import default_cells

cells = default_cells()
```

This expands to:

- `AxonCellConfig()`
- `XLCellConfig()`
- `mLSTMCellConfig()`
- `sLSTMCellConfig()`

### Cores

Low-level core configs live in `cortex.config`; runtime core modules live in `cortex.cores`.

| Core | Config | Description | Triton Accelerated | CUDA Accelerated |
| ---- | ------ | ----------- | ------------------ | ---------------- |
| `LSTMCore` | `LSTMCoreConfig` | LSTM wrapper with TensorDict state (`h`, `c`), step/sequence parity, and optional resets | Yes | No |
| `mLSTMCore` | `mLSTMCoreConfig` | Matrix-LSTM with per-head state, chunked closed-form updates, and optional causal Conv1D preprocessing | Yes | No |
| `sLSTMCore` | `sLSTMCoreConfig` | Structured LSTM with stabilized accumulators (`c`, `n`, `m`) and optional causal Conv1D preprocessing | Yes | No |
| `CausalConv1dCore` | `CausalConv1dCoreConfig` | Depthwise causal Conv1D memory with ring-buffer state and optional channel mixing | Yes (channel-mixing mode) | No |
| `AxonCore` | `AxonCoreConfig` | Streaming RTU with diagonal recurrent transitions and stateful linear dynamics | Yes | Yes |
| `XLCore` | `XLCoreConfig` | Transformer-XL style multi-head attention with rolling memory and optional Axon-backed Q/K/V projections | No | No |
| `AGaLiTeCore` | `AGaLiTeCoreConfig` | Attention-style recurrent discounted state with fused discounted-sum support | No | Yes |

Notes:

- Triton kernels are selected automatically on CUDA when constraints are satisfied; otherwise PyTorch fallback is used
- resets are optional and broadcast-safe: `[B, T]` in sequence mode and `[B]` in step mode
- `HFLlamaLayerConfig` is also available for wrapping Hugging Face LLaMA decoder layers inside a `CortexStack`

### Scaffolds

Scaffolds wrap cores with projection, gating, routing, and residual structure.

| Scaffold | Config | Description |
| -------- | ------ | ----------- |
| `PassThroughScaffold` | `PassThroughScaffoldConfig` | Runs the core directly at `d_hidden` with residual connection; no learned up/down projection |
| `PreUpScaffold` | `PreUpScaffoldConfig` | Projects to `d_inner = int(proj_factor * d_hidden)`, runs the core at `d_inner`, then projects back |
| `PreUpGatedScaffold` | `PreUpGatedScaffoldConfig` | Pre-up scaffold with GRU-style gating around the transformed path |
| `PostUpScaffold` | `PostUpScaffoldConfig` | Runs the core at `d_hidden`, then applies an FFN-style up/down projection before the residual merge |
| `PostUpGatedScaffold` | `PostUpGatedScaffoldConfig` | Post-up scaffold with GTrXL-style gating, useful for deeper stacks |
| `AdapterScaffold` | `AdapterScaffoldConfig` | Wraps another scaffold with an identity-initialized trainable residual adapter |
| `ColumnScaffold` | `ColumnScaffoldConfig` | Runs multiple expert scaffolds in parallel and mixes them through a router |

### Hidden Size Inference in Scaffolds

Some scaffolds control the working dimension of their nested core and will override the core's `hidden_size` when
building through `CortexStackConfig` or the auto builders.

Scaffolds that set the core hidden size:

- `PassThroughScaffold`: `core.hidden_size = d_hidden`
- `PostUpScaffold`: `core.hidden_size = d_hidden`
- `PostUpGatedScaffold`: `core.hidden_size = d_hidden`
- `PreUpScaffold`: `core.hidden_size = int(proj_factor * d_hidden)`
- `PreUpGatedScaffold`: `core.hidden_size = int(proj_factor * d_hidden)`

Best practice is to make this explicit by setting `hidden_size=None` in the core config:

```python
from cortex.config import LSTMCoreConfig, PreUpScaffoldConfig

cfg = PreUpScaffoldConfig(
    core=LSTMCoreConfig(hidden_size=None, num_layers=2),
    proj_factor=2.0,
)
```

If you instantiate scaffolds and cores manually without the stack builder, you must satisfy these dimension
relationships yourself.

## Column and MoE Routing

`ColumnScaffold` is the mixture-of-experts building block used by the auto stack builders. A Column runs multiple expert
scaffolds in parallel and mixes their deltas with:

- a global prior router
- optional per-token refinement
- an expert-axis mixer
- outer ReZero-style residual control

Build a Column from explicit cells:

```python
from cortex import CellConfig, RouterConfig, build_column_auto_config
from cortex.cells import AxonCellConfig, XLCellConfig
from cortex.config import PostUpScaffoldConfig, XLCoreConfig, sLSTMCoreConfig

col_cfg = build_column_auto_config(
    d_hidden=256,
    cells=[
        AxonCellConfig(),
        XLCellConfig(core=XLCoreConfig(mem_len=128, use_axon_qkv=True)),
        CellConfig(
            scaffold=PostUpScaffoldConfig(proj_factor=1.5),
            core=sLSTMCoreConfig(num_heads=4),
        ),
    ],
    router=RouterConfig(top_k=2, temperature=0.7, whisper_lambda=0.1),
)
```

You can also pass raw scaffold configs directly to `cells=[...]` when you want exact expert definitions.

### Compact Forward Pass

For a token `t`, the Column behaves conceptually like:

$$
\begin{aligned}
u_t &:= \mathrm{RMSNorm}(x_t) \\
y_{t,i} &= \mathrm{Scaffold}_i(u_t) \\
\Delta_{t,i} &= y_{t,i} - u_t \\
\tilde{\Delta}_{t,i} &= \Delta_{t,i} + \mathrm{Mixer}(\Delta)_{t,i} \\
\alpha_t &= \mathrm{softmax}\!\big(\log \mathrm{softmax}(z_g) + \lambda \hat{p}_t\big) \\
r_t &= \sum_i \alpha_{t,i}\,\tilde{\Delta}_{t,i} + (u_t - x_t) \\
y_{\mathrm{total}}(t) &= x_t + r_t \\
\mathrm{out}_t &= y_{\mathrm{total}}(t) + \alpha_{\mathrm{col}} \cdot \rho(r_t)\, .
\end{aligned}
$$

In practice, this gives you routed expert mixing while preserving the clean stack interface.

## Advanced Setup

### Manual Stack Construction

For full control, construct a `CortexStackConfig` directly:

```python
import torch
from cortex import CortexStackConfig, build_cortex
from cortex.config import LSTMCoreConfig, PassThroughScaffoldConfig, PreUpScaffoldConfig

cfg = CortexStackConfig(
    d_hidden=256,
    scaffolds=[
        PreUpScaffoldConfig(
            core=LSTMCoreConfig(hidden_size=None, num_layers=2),
            proj_factor=2.0,
        ),
        PassThroughScaffoldConfig(
            core=LSTMCoreConfig(hidden_size=256, num_layers=1),
        ),
    ],
    post_norm=True,
)

stack = build_cortex(cfg)
state = stack.init_state(batch=4, device="cpu", dtype=torch.float32)
x = torch.randn(4, 16, 256)
out, state = stack(x, state)
```

### Manual Column Construction

If you want exact control over a routed layer, build the `ColumnScaffoldConfig` first and place it inside a stack:

```python
from cortex import CortexStackConfig, RouterConfig, build_column_auto_config, build_cortex
from cortex.cells import AxonCellConfig, mLSTMCellConfig

column = build_column_auto_config(
    d_hidden=256,
    cells=[AxonCellConfig(), mLSTMCellConfig()],
    router=RouterConfig(top_k=1),
)

stack = build_cortex(
    CortexStackConfig(
        d_hidden=256,
        scaffolds=[column],
        post_norm=True,
    )
)
```

### Hugging Face LLaMA Integration

`cortex.stacks` can wrap LLaMA decoder layers inside a `CortexStack`:

```python
from cortex.stacks import build_hf_stack

stack = build_hf_stack(
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    num_layers=8,
    mem_len=128,
    compile_blocks=False,
)
```

This integration is currently LLaMA-focused.

## AxonLayer

`AxonLayer` is a stateful linear-like module built on top of `AxonCore`. It behaves like:

```text
y = Linear(x) + AxonCore(x, state)
```

but stores its recurrent substate inside a caller-provided parent `TensorDict`. This makes it useful as a drop-in
stateful replacement for selected `nn.Linear` paths inside custom cores.

```python
import torch
from tensordict import TensorDict
from cortex import AxonCoreConfig, AxonLayer, MemoryCore
from cortex.cores.core.axon_layer import update_parent_state


class MyCore(MemoryCore):
    def __init__(self, hidden_size: int) -> None:
        super().__init__(hidden_size=hidden_size)
        self.proj = AxonLayer(
            hidden_size,
            hidden_size,
            cfg=AxonCoreConfig(hidden_size=hidden_size, out_dim=hidden_size),
            name="proj",
            group="mycore",
        )

    def init_state(self, batch: int, *, device: torch.device | str, dtype: torch.dtype) -> TensorDict:
        return TensorDict({}, batch_size=[batch], device=torch.device(device))

    def forward(self, x, state, *, resets=None):
        if state is None:
            state = self.init_state(x.shape[0], device=x.device, dtype=x.dtype)
        y = self.proj(x, state=state, resets=resets)
        next_state = TensorDict({}, batch_size=[x.shape[0]], device=x.device)
        update_parent_state(next_state, state)
        return y, next_state

    def reset_state(self, state, mask):
        return self.proj.reset_state(mask, state=state)
```

### Internal Structure

Internally, `AxonLayer` combines:

- a plain linear branch
- an `AxonCore` branch with local recurrent dynamics
- parent-state integration through `TensorDict`

Important properties:

- **State-augmented linear projection**: adds temporal structure to a linear-like path
- **Optional SRHT mixing**: improves conditioning for diagonal recurrent updates
- **Streaming traces**: supports long-horizon gradient flow with compact state

### AxonLayer Integration Across Cores

Several cores can opt into Axon-backed internal projections:

| Core | Components Replaced | Flags |
| ---- | ------------------- | ----- |
| `sLSTMCore` | fused gate projections | `use_axon_layer` |
| `mLSTMCore` | input/forget gates and optional QKV path | `use_axon_layer`, `use_axon_qkv` |
| `XLCore` | Q/K/V projections | `use_axon_qkv` |

The built-in cells that use these options can still be specified directly through their cell configs.

## Evaluate Quickly

Cortex includes lightweight synthetic evaluations for sanity checking stacks and recipes.

Available tasks:

- `delayed_recall`
- `majority`
- `dyck`

Run a single stack:

```bash
uv run python packages/cortex/evaluations/run.py --task delayed_recall --stack slstm_postup
```

Run all registered evaluation stacks:

```bash
uv run python packages/cortex/evaluations/run.py --task majority --stack all
```

Common flags:

- `--epochs`
- `--batch-size`
- `--lr`
- `--seed`
- `--log-level {DEBUG, INFO, WARNING, ERROR}`

More detail is in [evaluations/README.md](./evaluations/README.md).

## Backend Configuration

Cortex selects between Triton, CUDA, and PyTorch implementations based on availability and per-core constraints.

You can force the PyTorch path with:

```bash
CORTEX_DISABLE_TRITON=1 python your_script.py
```

or:

```bash
CORTEX_FORCE_PYTORCH=1 python your_script.py
```

Use this when:

- debugging numerical differences between backends
- testing on a machine without Triton
- forcing a simpler execution path during development

## Extending Cortex

Cortex is registry-driven. New cores and scaffolds become available to the config system once registered.

### Custom Core

```python
import torch
from tensordict import TensorDict
from cortex import CoreConfig, MemoryCore, register_core


class GRUCoreConfig(CoreConfig):
    num_layers: int = 1


@register_core(GRUCoreConfig)
class GRUCore(MemoryCore):
    def __init__(self, cfg: GRUCoreConfig) -> None:
        super().__init__(hidden_size=cfg.hidden_size)
        self.net = torch.nn.GRU(
            input_size=cfg.hidden_size,
            hidden_size=cfg.hidden_size,
            num_layers=cfg.num_layers,
            batch_first=True,
        )
        self.num_layers = cfg.num_layers

    def init_state(self, batch: int, *, device: torch.device | str, dtype: torch.dtype) -> TensorDict:
        h = torch.zeros(batch, self.num_layers, self.hidden_size, device=device, dtype=dtype)
        return TensorDict({"h": h}, batch_size=[batch])

    def forward(self, x, state, *, resets=None):
        ...

    def reset_state(self, state, mask):
        ...
```

### Custom Scaffold

```python
from cortex import BaseScaffold, ScaffoldConfig, register_scaffold


class GatedResidualScaffoldConfig(ScaffoldConfig):
    gate_bias: float = 0.0


@register_scaffold(GatedResidualScaffoldConfig)
class GatedResidualScaffold(BaseScaffold):
    def forward(self, x, state, *, resets=None):
        ...
```

Both custom cores and scaffolds are then usable inside stack configs and builder flows.

### Custom Cell Presets and Stack Recipes

If you want a reusable programmer-facing cell preset, define it as a composed `CellConfig`:

```python
from cortex import CellConfig
from cortex.config import PostUpScaffoldConfig, XLCoreConfig


def LongMemXLCell() -> CellConfig:
    return CellConfig(
        scaffold=PostUpScaffoldConfig(proj_factor=2.0),
        core=XLCoreConfig(mem_len=512, use_axon_qkv=True),
    )
```

Then use it directly in a stack recipe:

```python
from cortex.stacks import build_cortex_auto_stack

stack = build_cortex_auto_stack(
    d_hidden=256,
    layers=[
        [LongMemXLCell()],
        [LongMemXLCell()],
    ],
)
```

Complete worked examples:

- [examples/custom_cell_example.py](./examples/custom_cell_example.py)
- [examples/custom_block_example.py](./examples/custom_block_example.py)
- [examples/adapter_example.py](./examples/adapter_example.py)

## Package Layout

- `cortex.cells`: public composed cell configs
- `cortex.config`: low-level config models
- `cortex.cores`: core implementations and registration
- `cortex.scaffolds`: scaffold implementations, columns, and builders
- `cortex.stacks`: stack classes and auto-builders

For most use cases:

1. choose cells in `cortex.cells`
2. build with `cortex.stacks.build_cortex_auto_stack`
3. drop to `cortex.config` when you want exact low-level control
