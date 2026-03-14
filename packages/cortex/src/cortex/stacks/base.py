"""Sequential stack with optional per-scaffold torch.compile."""

from __future__ import annotations

import logging
from typing import Optional

import torch
import torch.nn as nn
from tensordict import TensorDict

from cortex.config import CortexStackConfig
from cortex.cores import build_core
from cortex.routed_adapter import apply_routed_adapter_, use_route_ids
from cortex.scaffolds import ColumnScaffold, build_scaffold
from cortex.scaffolds.base import BaseScaffold
from cortex.types import MaybeState, ResetMask, Tensor

logger = logging.getLogger(__name__)


class CortexStack(nn.Module):
    """Stack of scaffolds that preserves external hidden size."""

    def __init__(self, cfg: CortexStackConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self._routed_adapter_cfg = (
            cfg.routed_adapter if cfg.routed_adapter is not None and cfg.routed_adapter.enabled else None
        )

        self.scaffolds = nn.ModuleList(self._build_scaffolds(cfg))
        self.norm = nn.LayerNorm(cfg.d_hidden) if cfg.post_norm else nn.Identity()
        self._compiled_scaffolds: list | None = None
        self._routed_adapter_replaced_modules: int = 0

        compile_requested = bool(getattr(cfg, "compile_scaffolds", False))
        if self._routed_adapter_cfg is not None:
            self._routed_adapter_replaced_modules = apply_routed_adapter_(self, self._routed_adapter_cfg)
            if compile_requested:
                logger.warning("Disabling scaffold compilation for CortexStack: routed_adapter is enabled.")
                compile_requested = False

        if compile_requested and not torch.cuda.is_available():
            logger.warning("Disabling scaffold compilation for CortexStack: running on CPU.")
            compile_requested = False

        if compile_requested and hasattr(torch, "compile"):
            compiled: list[nn.Module] = []
            for scaffold in self.scaffolds:
                if isinstance(scaffold, ColumnScaffold):
                    scaffold._compiled_experts = [torch.compile(expert) for expert in scaffold.experts]  # type: ignore[attr-defined]
                    compiled.append(scaffold)
                else:
                    compiled.append(torch.compile(scaffold))
            self._compiled_scaffolds = compiled

    def _build_scaffolds(self, cfg: CortexStackConfig) -> list[BaseScaffold]:
        scaffolds: list[BaseScaffold] = []
        d_hidden = cfg.d_hidden

        for scaffold_cfg in cfg.scaffolds:
            if scaffold_cfg.core is None:
                scaffold = build_scaffold(config=scaffold_cfg, d_hidden=d_hidden, core=None)
            else:
                core_hidden_size = scaffold_cfg.get_core_hidden_size(d_hidden)
                dumped = scaffold_cfg.core.model_dump()
                dumped["hidden_size"] = core_hidden_size
                core_config = type(scaffold_cfg.core)(**dumped)
                core = build_core(core_config)
                scaffold = build_scaffold(config=scaffold_cfg, d_hidden=d_hidden, core=core)

            scaffolds.append(scaffold)

        return scaffolds

    def init_state(self, batch: int, *, device: torch.device | str = "cpu", dtype: torch.dtype) -> TensorDict:
        state = TensorDict({}, batch_size=[batch], device=torch.device(device))
        for i, scaffold in enumerate(self.scaffolds):
            scaffold_key = f"{scaffold.__class__.__name__}_{i}"
            state[scaffold_key] = scaffold.init_state(batch=batch, device=device, dtype=dtype)
        return state

    def _validate_route_ids(
        self,
        route_ids: torch.Tensor | None,
        *,
        batch_size: int,
        device: torch.device,
    ) -> torch.Tensor | None:
        if self._routed_adapter_cfg is None:
            return None
        if route_ids is None:
            raise ValueError("Routed adapters are enabled; pass route_ids with shape [B] to CortexStack.forward/step.")

        ids = torch.as_tensor(route_ids, device=device, dtype=torch.long)
        if ids.dim() != 1 or ids.shape[0] != batch_size:
            raise ValueError(f"route_ids must have shape [{batch_size}], got {tuple(ids.shape)}")
        if bool((ids < 0).any()) or bool((ids >= self._routed_adapter_cfg.num_slots).any()):
            raise ValueError(
                f"route_ids values must be in [0, {self._routed_adapter_cfg.num_slots}), "
                f"got min={ids.min()} max={ids.max()}"
            )
        return ids

    def forward(
        self,
        x: Tensor,
        state: MaybeState = None,
        *,
        resets: Optional[ResetMask] = None,
        route_ids: torch.Tensor | None = None,
    ) -> tuple[Tensor, MaybeState]:
        y = x
        batch_size = x.shape[0]
        ids = self._validate_route_ids(route_ids, batch_size=batch_size, device=x.device)
        next_state = TensorDict({}, batch_size=[batch_size])
        with use_route_ids(ids):
            for i, scaffold in enumerate(self.scaffolds):
                scaffold_key = f"{scaffold.__class__.__name__}_{i}"
                if isinstance(state, TensorDict):
                    scaffold_state = state.get(scaffold_key)
                    if scaffold_state is None:
                        scaffold_state = TensorDict({}, batch_size=[batch_size], device=y.device)
                else:
                    scaffold_state = TensorDict({}, batch_size=[batch_size], device=y.device)
                if self._compiled_scaffolds is not None and torch.is_grad_enabled():
                    call = self._compiled_scaffolds[i]
                else:
                    call = scaffold
                y, scaffold_next_state = call(y, scaffold_state, resets=resets)
                next_state[scaffold_key] = (
                    scaffold_next_state
                    if isinstance(scaffold_next_state, TensorDict)
                    else TensorDict({}, batch_size=[batch_size])
                )
        y = self.norm(y)
        return y, next_state

    def step(
        self,
        x: Tensor,
        state: MaybeState = None,
        **kwargs,
    ) -> tuple[Tensor, MaybeState]:
        """Single timestep forward pass."""
        return self.forward(x, state, **kwargs)

    def reset_state(self, state: MaybeState, mask: ResetMask) -> MaybeState:
        if state is None or not isinstance(state, TensorDict):
            return state
        batch_size = state.batch_size[0] if state.batch_size else mask.shape[0]
        new_state = TensorDict({}, batch_size=[batch_size], device=state.device)
        for i, scaffold in enumerate(self.scaffolds):
            scaffold_key = f"{scaffold.__class__.__name__}_{i}"
            new_state[scaffold_key] = scaffold.reset_state(state.get(scaffold_key), mask)
        return new_state


__all__ = ["CortexStack"]
