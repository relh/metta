"""Multiscale recurrent stack with a shared trunk and one full tower per split."""

from __future__ import annotations

import logging
from typing import Sequence, cast

import torch
import torch.nn as nn
from pydantic import BaseModel
from tensordict import TensorDict

from cortex.cells import CellConfig as PublicCellConfig
from cortex.cells import default_cells
from cortex.config import MultiScaleLayerConfig, MultiScaleStackConfig, RouterConfig, ScaffoldConfig
from cortex.cores import build_cell
from cortex.scaffolds import BaseBlock, ColumnBlock, build_block
from cortex.scaffolds.column.auto import build_column_auto_config
from cortex.types import MaybeState, ResetMask, Tensor

logger = logging.getLogger(__name__)


class MultiScaleStack(nn.Module):
    def __init__(self, cfg: MultiScaleStackConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self._periods = [layer.period for layer in cfg.layers]
        self._shared_layer_count = int(cfg.split_start_layer)
        self._splits = list(cfg.splits)

        self.shared_layers = nn.ModuleList(
            self._build_layer_modules(cfg.layers[: self._shared_layer_count], d_hidden=cfg.d_hidden)
        )

        split_layer_cfgs = cfg.layers[self._shared_layer_count :]
        self.split_layers = nn.ModuleDict(
            {
                split: nn.ModuleList(self._build_layer_modules(split_layer_cfgs, d_hidden=cfg.d_hidden))
                for split in self._splits
            }
        )

        def make_norm() -> nn.Module:
            return nn.LayerNorm(cfg.d_hidden) if cfg.post_norm else nn.Identity()

        self.trunk_norm = make_norm()
        self.split_norms = nn.ModuleDict({split: make_norm() for split in self._splits})

        self._compiled_shared_layers: list[nn.Module] | None = None
        self._compiled_split_layers: dict[str, list[nn.Module]] | None = None
        self._split_cuda_streams: dict[str, torch.cuda.Stream] | None = None

        compile_requested = bool(cfg.compile_blocks)
        if compile_requested and not torch.cuda.is_available():
            logger.warning("Disabling block compilation for MultiScaleStack: running on CPU.")
            compile_requested = False
        if compile_requested and hasattr(torch, "compile"):
            self._compiled_shared_layers = self._compile_layers_for_training(self.shared_layers)
            self._compiled_split_layers = {
                split: self._compile_layers_for_training(split_layers)
                for split, split_layers in self.split_layers.items()
            }

    def _build_layer_modules(self, layer_cfgs: Sequence[MultiScaleLayerConfig], *, d_hidden: int) -> list[BaseBlock]:
        layers: list[BaseBlock] = []
        for layer_cfg in layer_cfgs:
            block_cfg = layer_cfg.block
            if block_cfg.cell is None:
                block = build_block(config=block_cfg, d_hidden=d_hidden, cell=None)
            else:
                cell_hidden_size = block_cfg.get_cell_hidden_size(d_hidden)
                dumped = block_cfg.cell.model_dump()
                dumped["hidden_size"] = cell_hidden_size
                cell_config = type(block_cfg.cell)(**dumped)
                cell = build_cell(cell_config)
                block = build_block(config=block_cfg, d_hidden=d_hidden, cell=cell)
            layers.append(block)
        return layers

    def _compile_layers_for_training(self, layers: Sequence[BaseBlock]) -> list[nn.Module]:
        compiled: list[nn.Module] = []
        for layer in layers:
            if isinstance(layer, ColumnBlock):
                layer._compiled_experts = [torch.compile(expert) for expert in layer.experts]  # type: ignore[attr-defined]
                compiled.append(layer)
            else:
                compiled.append(torch.compile(layer))
        return compiled

    @staticmethod
    def _select_layer_call(
        compiled_layers: Sequence[nn.Module] | None,
        idx: int,
        layer: BaseBlock,
    ) -> nn.Module:
        if compiled_layers is not None and torch.is_grad_enabled():
            return compiled_layers[idx]
        return layer

    def _updates_for_layer(self, layer_idx: int) -> int:
        return self.cfg.num_inner_steps // self._periods[layer_idx]

    def _stride_between_layers(self, lower_idx: int, upper_idx: int) -> int:
        return self._periods[upper_idx] // self._periods[lower_idx]

    def _layer_key(self, layer_idx: int) -> str:
        return f"layer_{layer_idx}"

    def _split_output_key(self, split: str) -> str:
        return f"multiscale_split_{split}_out"

    def init_state(self, batch: int, *, device: torch.device | str = "cpu", dtype: torch.dtype) -> TensorDict:
        shared_state = TensorDict({}, batch_size=[batch], device=torch.device(device))
        for idx, layer in enumerate(self.shared_layers):
            shared_state.set(self._layer_key(idx), layer.init_state(batch=batch, device=device, dtype=dtype))

        split_states = TensorDict({}, batch_size=[batch], device=torch.device(device))
        for split, split_layers in self.split_layers.items():
            split_state = TensorDict({}, batch_size=[batch], device=torch.device(device))
            for local_idx, layer in enumerate(split_layers):
                global_idx = self._shared_layer_count + local_idx
                split_state.set(
                    self._layer_key(global_idx),
                    layer.init_state(batch=batch, device=device, dtype=dtype),
                )
            split_states.set(split, split_state)

        return TensorDict(
            {"shared": shared_state, "splits": split_states},
            batch_size=[batch],
            device=torch.device(device),
        )

    def _normalize_resets(
        self,
        resets: ResetMask | None,
        *,
        batch_size: int,
        time_steps: int,
        device: torch.device,
    ) -> torch.Tensor | None:
        if resets is None:
            return None
        mask = torch.as_tensor(resets, device=device, dtype=torch.bool)
        if mask.dim() == 1 and mask.shape[0] == batch_size:
            return mask[:, None].expand(-1, time_steps)
        if mask.dim() != 2 or mask.shape != (batch_size, time_steps):
            raise ValueError(
                f"resets must have shape [{batch_size}] or [{batch_size}, {time_steps}], got {tuple(mask.shape)}"
            )
        return mask

    def forward(
        self,
        x: Tensor,
        state: MaybeState = None,
        *,
        resets: ResetMask | None = None,
    ) -> tuple[TensorDict, MaybeState]:
        return self._forward_parallel(x, state, resets=resets)

    def _forward_parallel(
        self,
        x: Tensor,
        state: MaybeState = None,
        *,
        resets: ResetMask | None = None,
    ) -> tuple[TensorDict, MaybeState]:
        step_mode = x.dim() == 2
        x_outer = x[:, None, :] if step_mode else x
        if x_outer.dim() != 3:
            raise ValueError(f"MultiScaleStack expects [B, H] or [B, T, H] input, got {tuple(x.shape)}")

        batch_size, time_steps, _hidden = x_outer.shape
        if state is None:
            current_state = self.init_state(batch=batch_size, device=x_outer.device, dtype=x_outer.dtype)
        else:
            current_state = cast(TensorDict, state.clone(recurse=True))

        reset_mask = self._normalize_resets(resets, batch_size=batch_size, time_steps=time_steps, device=x_outer.device)
        outputs, current_state = self._forward_parallel_impl(x_outer, current_state, reset_mask)
        if step_mode:
            return _squeeze_output_td(outputs), current_state
        return outputs, current_state

    def _forward_outer_loop(
        self,
        x: Tensor,
        state: MaybeState = None,
        *,
        resets: ResetMask | None = None,
    ) -> tuple[TensorDict, MaybeState]:
        step_mode = x.dim() == 2
        x_outer = x[:, None, :] if step_mode else x
        if x_outer.dim() != 3:
            raise ValueError(f"MultiScaleStack expects [B, H] or [B, T, H] input, got {tuple(x.shape)}")

        batch_size, time_steps, _hidden = x_outer.shape
        if state is None:
            current_state = self.init_state(batch=batch_size, device=x_outer.device, dtype=x_outer.dtype)
        else:
            current_state = cast(TensorDict, state.clone(recurse=True))

        reset_mask = self._normalize_resets(resets, batch_size=batch_size, time_steps=time_steps, device=x_outer.device)

        output_lists = self._empty_output_lists()
        for step_idx in range(time_steps):
            if reset_mask is not None and bool(reset_mask[:, step_idx].any()):
                current_state = cast(TensorDict, self.reset_state(current_state, reset_mask[:, step_idx]))
            step_outputs, current_state = self._forward_outer_step(x_outer[:, step_idx], current_state)
            for key in output_lists:
                output_lists[key].append(step_outputs.get(key))

        outputs = _stack_output_lists(output_lists, device=x_outer.device)
        if step_mode:
            return _squeeze_output_td(outputs), current_state
        return outputs, current_state

    def _forward_parallel_impl(
        self,
        x_outer: torch.Tensor,
        state: TensorDict,
        reset_mask: torch.Tensor | None,
    ) -> tuple[TensorDict, TensorDict]:
        boundary_outer_inner, state = self._forward_shared_parallel(x_outer, state, reset_mask)
        outputs: dict[str, torch.Tensor] = {
            "multiscale_trunk_out": self.trunk_norm(boundary_outer_inner[:, :, -1]),
        }
        split_outputs, state = self._forward_splits_parallel(boundary_outer_inner, state, reset_mask)
        outputs.update(split_outputs)
        return _make_output_td(
            outputs,
            batch_size=list(boundary_outer_inner.shape[:2]),
            device=boundary_outer_inner.device,
        ), state

    def _forward_shared_parallel(
        self,
        x_outer: torch.Tensor,
        state: TensorDict,
        reset_mask: torch.Tensor | None,
    ) -> tuple[torch.Tensor, TensorDict]:
        time_steps = x_outer.shape[1]
        shared_state = cast(TensorDict, state["shared"])
        current_outer_inner = _repeat_outer_sequence(x_outer, self._updates_for_layer(0))

        for shared_idx, layer in enumerate(self.shared_layers):
            layer_key = self._layer_key(shared_idx)
            layer_state = cast(TensorDict, shared_state[layer_key])
            current_seq = _flatten_outer_inner(current_outer_inner)
            layer_resets = _expand_outer_resets(reset_mask, updates=current_outer_inner.shape[2])
            call = self._select_layer_call(self._compiled_shared_layers, shared_idx, layer)
            current_seq, next_layer_state = call(current_seq, layer_state, resets=layer_resets)
            shared_state.set(layer_key, next_layer_state)
            current_outer_inner = _unflatten_outer_inner(current_seq, time_steps=time_steps)
            if shared_idx + 1 < self._shared_layer_count:
                current_outer_inner = _stride_outer_sequence(
                    current_outer_inner,
                    self._stride_between_layers(shared_idx, shared_idx + 1),
                )

        return current_outer_inner, state

    def _forward_splits_parallel(
        self,
        boundary_outer_inner: torch.Tensor,
        state: TensorDict,
        reset_mask: torch.Tensor | None,
    ) -> tuple[dict[str, torch.Tensor], TensorDict]:
        split_states = cast(TensorDict, state["splits"])
        first_stride = self._stride_between_layers(self._shared_layer_count - 1, self._shared_layer_count)
        split_outputs: dict[str, torch.Tensor] = {}

        split_results: dict[str, tuple[TensorDict, torch.Tensor]] = {}
        can_parallel = self._can_parallelize_splits(boundary_outer_inner)
        streams = self._split_streams(boundary_outer_inner.device) if can_parallel else None
        current_stream = torch.cuda.current_stream(boundary_outer_inner.device) if can_parallel else None

        if can_parallel:
            assert streams is not None
            assert current_stream is not None
            for split, split_layers in self.split_layers.items():
                stream = streams[split]
                stream.wait_stream(current_stream)
                with torch.cuda.stream(stream):
                    split_results[split] = self._run_split_parallel_tower(
                        boundary_outer_inner=boundary_outer_inner,
                        reset_mask=reset_mask,
                        split=split,
                        split_layers=split_layers,
                        split_state=cast(TensorDict, split_states[split]),
                        first_stride=first_stride,
                    )
            for stream in streams.values():
                current_stream.wait_stream(stream)
        else:
            split_results = {
                split: self._run_split_parallel_tower(
                    boundary_outer_inner=boundary_outer_inner,
                    reset_mask=reset_mask,
                    split=split,
                    split_layers=split_layers,
                    split_state=cast(TensorDict, split_states[split]),
                    first_stride=first_stride,
                )
                for split, split_layers in self.split_layers.items()
            }

        for split, (split_state, split_output) in split_results.items():
            split_states.set(split, split_state)
            split_outputs[self._split_output_key(split)] = self.split_norms[split](split_output)

        return split_outputs, state

    def _run_split_parallel_tower(
        self,
        *,
        boundary_outer_inner: torch.Tensor,
        reset_mask: torch.Tensor | None,
        split: str,
        split_layers: nn.ModuleList,
        split_state: TensorDict,
        first_stride: int,
    ) -> tuple[TensorDict, torch.Tensor]:
        split_outer_inner = _stride_outer_sequence(boundary_outer_inner, first_stride)
        time_steps = boundary_outer_inner.shape[1]

        for local_idx, layer in enumerate(split_layers):
            global_idx = self._shared_layer_count + local_idx
            layer_key = self._layer_key(global_idx)
            layer_state = cast(TensorDict, split_state[layer_key])
            split_seq = _flatten_outer_inner(split_outer_inner)
            layer_resets = _expand_outer_resets(reset_mask, updates=split_outer_inner.shape[2])
            compiled_layers = self._compiled_split_layers[split] if self._compiled_split_layers is not None else None
            call = self._select_layer_call(compiled_layers, local_idx, layer)
            split_seq, next_layer_state = call(split_seq, layer_state, resets=layer_resets)
            split_state.set(layer_key, next_layer_state)
            split_outer_inner = _unflatten_outer_inner(split_seq, time_steps=time_steps)
            if global_idx + 1 < len(self.cfg.layers):
                split_outer_inner = _stride_outer_sequence(
                    split_outer_inner,
                    self._stride_between_layers(global_idx, global_idx + 1),
                )

        return split_state, split_outer_inner[:, :, -1]

    def _forward_outer_step(
        self,
        x_t: torch.Tensor,
        state: TensorDict,
    ) -> tuple[TensorDict, TensorDict]:
        shared_state = cast(TensorDict, state["shared"])
        current_seq = repeat_sequence(x_t, self._updates_for_layer(0))

        for shared_idx, layer in enumerate(self.shared_layers):
            layer_key = self._layer_key(shared_idx)
            layer_state = cast(TensorDict, shared_state[layer_key])
            call = self._select_layer_call(self._compiled_shared_layers, shared_idx, layer)
            current_seq, next_layer_state = call(current_seq, layer_state)
            shared_state.set(layer_key, next_layer_state)
            if shared_idx + 1 < self._shared_layer_count:
                current_seq = stride_sequence(current_seq, self._stride_between_layers(shared_idx, shared_idx + 1))

        outputs: dict[str, torch.Tensor] = {
            "multiscale_trunk_out": self.trunk_norm(current_seq[:, -1]),
        }
        split_states = cast(TensorDict, state["splits"])
        first_stride = self._stride_between_layers(self._shared_layer_count - 1, self._shared_layer_count)

        for split, split_layers in self.split_layers.items():
            split_state = cast(TensorDict, split_states[split])
            split_seq = stride_sequence(current_seq, first_stride)
            for local_idx, layer in enumerate(split_layers):
                global_idx = self._shared_layer_count + local_idx
                layer_key = self._layer_key(global_idx)
                previous_layer_state = cast(TensorDict, split_state[layer_key])
                compiled_layers = (
                    self._compiled_split_layers[split] if self._compiled_split_layers is not None else None
                )
                call = self._select_layer_call(compiled_layers, local_idx, layer)
                split_seq, next_layer_state = call(split_seq, previous_layer_state)
                split_state.set(layer_key, next_layer_state)
                if global_idx + 1 < len(self.cfg.layers):
                    split_seq = stride_sequence(split_seq, self._stride_between_layers(global_idx, global_idx + 1))
            outputs[self._split_output_key(split)] = self.split_norms[split](split_seq[:, -1])

        return _make_output_td(outputs, batch_size=[x_t.shape[0]], device=x_t.device), state

    def step(
        self,
        x: Tensor,
        state: MaybeState = None,
        **kwargs,
    ) -> tuple[TensorDict, MaybeState]:
        return self.forward(x, state, **kwargs)

    def reset_state(self, state: MaybeState, mask: ResetMask) -> MaybeState:
        if state is None or not isinstance(state, TensorDict):
            return state

        shared_state = cast(TensorDict, state["shared"])
        split_states = cast(TensorDict, state["splits"])
        batch_size = state.batch_size[0] if state.batch_size else mask.shape[0]
        new_state = TensorDict({}, batch_size=[batch_size], device=state.device)

        new_shared_state = TensorDict({}, batch_size=[batch_size], device=state.device)
        for shared_idx, layer in enumerate(self.shared_layers):
            layer_key = self._layer_key(shared_idx)
            new_shared_state.set(layer_key, layer.reset_state(shared_state[layer_key], mask))
        new_state.set("shared", new_shared_state)

        new_split_states = TensorDict({}, batch_size=[batch_size], device=state.device)
        for split, split_layers in self.split_layers.items():
            split_state = cast(TensorDict, split_states[split])
            new_split_state = TensorDict({}, batch_size=[batch_size], device=state.device)
            for local_idx, layer in enumerate(split_layers):
                global_idx = self._shared_layer_count + local_idx
                layer_key = self._layer_key(global_idx)
                new_split_state.set(layer_key, layer.reset_state(split_state[layer_key], mask))
            new_split_states.set(split, new_split_state)
        new_state.set("splits", new_split_states)

        return new_state

    def _can_parallelize_splits(self, tensor: torch.Tensor) -> bool:
        return len(self.split_layers) > 1 and tensor.is_cuda and torch.cuda.is_available()

    def _split_streams(self, device: torch.device) -> dict[str, torch.cuda.Stream]:
        if self._split_cuda_streams is None or set(self._split_cuda_streams) != set(self._splits):
            self._split_cuda_streams = {split: torch.cuda.Stream(device=device) for split in self._splits}
            return self._split_cuda_streams

        if any(stream.device != device for stream in self._split_cuda_streams.values()):
            self._split_cuda_streams = {split: torch.cuda.Stream(device=device) for split in self._splits}
        return self._split_cuda_streams

    def _empty_output_lists(self) -> dict[str, list[torch.Tensor]]:
        return {"multiscale_trunk_out": [], **{self._split_output_key(split): [] for split in self._splits}}


def repeat_sequence(x: torch.Tensor, repeats: int) -> torch.Tensor:
    return x.unsqueeze(1).expand(-1, repeats, -1)


def stride_sequence(x: torch.Tensor, stride: int) -> torch.Tensor:
    if stride == 1:
        return x
    return x[:, stride - 1 :: stride, :]


def _repeat_outer_sequence(x: torch.Tensor, repeats: int) -> torch.Tensor:
    return x.unsqueeze(2).expand(-1, -1, repeats, -1)


def _stride_outer_sequence(x: torch.Tensor, stride: int) -> torch.Tensor:
    if stride == 1:
        return x
    return x[:, :, stride - 1 :: stride, :]


def _flatten_outer_inner(x: torch.Tensor) -> torch.Tensor:
    batch_size, time_steps, updates, hidden = x.shape
    return x.reshape(batch_size, time_steps * updates, hidden)


def _unflatten_outer_inner(x: torch.Tensor, *, time_steps: int) -> torch.Tensor:
    batch_size, total_steps, hidden = x.shape
    if total_steps % time_steps != 0:
        raise ValueError(f"Cannot unflatten shape {tuple(x.shape)} with time_steps={time_steps}")
    updates = total_steps // time_steps
    return x.reshape(batch_size, time_steps, updates, hidden)


def _expand_outer_resets(reset_mask: torch.Tensor | None, *, updates: int) -> torch.Tensor | None:
    if reset_mask is None:
        return None
    batch_size, time_steps = reset_mask.shape
    expanded = torch.zeros(batch_size, time_steps * updates, device=reset_mask.device, dtype=reset_mask.dtype)
    expanded[:, ::updates] = reset_mask
    return expanded


def _make_output_td(outputs: dict[str, torch.Tensor], *, batch_size: list[int], device: torch.device) -> TensorDict:
    return TensorDict(outputs, batch_size=batch_size, device=device)


def _squeeze_output_td(td: TensorDict) -> TensorDict:
    squeezed = {key: value[:, 0] for key, value in td.items()}
    batch_size = [next(iter(squeezed.values())).shape[0]] if squeezed else [0]
    return TensorDict(squeezed, batch_size=batch_size, device=td.device)


def _stack_output_lists(output_lists: dict[str, list[torch.Tensor]], *, device: torch.device) -> TensorDict:
    stacked = {key: torch.stack(values, dim=1) for key, values in output_lists.items()}
    sample = next(iter(stacked.values()))
    return TensorDict(stacked, batch_size=list(sample.shape[:2]), device=device)


def build_multiscale_stack_config(
    *,
    d_hidden: int,
    num_inner_steps: int,
    periods: Sequence[int],
    splits: Sequence[str],
    split_start_layer: int,
    num_layers: int = 2,
    layers: Sequence[Sequence[PublicCellConfig | ScaffoldConfig]] | None = None,
    router: RouterConfig | None = None,
    post_norm: bool = True,
    compile_blocks: bool = True,
) -> MultiScaleStackConfig:
    configured_layers = _resolve_layers(num_layers=num_layers, layers=layers)
    if len(periods) != len(configured_layers):
        raise ValueError(f"periods length {len(periods)} must match number of layers {len(configured_layers)}")

    multiscale_layers = [
        MultiScaleLayerConfig(
            period=period,
            scaffold=build_column_auto_config(d_hidden=d_hidden, cells=layer_cells, router=router),
        )
        for period, layer_cells in zip(periods, configured_layers, strict=True)
    ]

    return MultiScaleStackConfig(
        layers=multiscale_layers,
        d_hidden=d_hidden,
        num_inner_steps=num_inner_steps,
        splits=list(splits),
        split_start_layer=split_start_layer,
        post_norm=post_norm,
        compile_blocks=bool(compile_blocks),
    )


def build_multiscale_stack(
    *,
    d_hidden: int,
    num_inner_steps: int,
    periods: Sequence[int],
    splits: Sequence[str],
    split_start_layer: int,
    num_layers: int = 2,
    layers: Sequence[Sequence[PublicCellConfig | ScaffoldConfig]] | None = None,
    router: RouterConfig | None = None,
    post_norm: bool = True,
    compile_blocks: bool = True,
) -> MultiScaleStack:
    cfg = build_multiscale_stack_config(
        d_hidden=d_hidden,
        num_inner_steps=num_inner_steps,
        periods=periods,
        splits=splits,
        split_start_layer=split_start_layer,
        num_layers=num_layers,
        layers=layers,
        router=router,
        post_norm=post_norm,
        compile_blocks=compile_blocks,
    )
    return MultiScaleStack(cfg)


def _resolve_layers(
    *,
    num_layers: int,
    layers: Sequence[Sequence[PublicCellConfig | ScaffoldConfig]] | None,
) -> list[list[PublicCellConfig | ScaffoldConfig]]:
    if layers is not None:
        configured_layers = [list(layer) for layer in layers]
        if not configured_layers:
            raise ValueError("layers produced no multiscale layers")
        return configured_layers
    return [[cast(PublicCellConfig, _clone_model(cell)) for cell in default_cells()] for _ in range(num_layers)]


def _clone_model(model: BaseModel) -> BaseModel:
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=True)
    return model.copy(deep=True)


__all__ = [
    "MultiScaleStack",
    "build_multiscale_stack",
    "build_multiscale_stack_config",
    "repeat_sequence",
    "stride_sequence",
]
