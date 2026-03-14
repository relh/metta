"""Adapter scaffold for adding trainable residual paths to pretrained models."""

from __future__ import annotations

import math
from typing import Optional, Tuple

import torch
import torch.nn as nn
from tensordict import TensorDict

from cortex.config import AdapterScaffoldConfig
from cortex.cores import build_core
from cortex.cores.base import MemoryCore
from cortex.scaffolds.base import BaseScaffold
from cortex.scaffolds.registry import build_scaffold, register_scaffold
from cortex.types import MaybeState, ResetMask, Tensor


@register_scaffold(AdapterScaffoldConfig)
class AdapterScaffold(BaseScaffold):
    """Wraps a scaffold with an identity-initialized gated bottleneck adapter for finetuning."""

    def __init__(self, config: AdapterScaffoldConfig, d_hidden: int, core: MemoryCore | None = None) -> None:
        assert config.base_scaffold.core is not None, "AdapterScaffold requires base_scaffold.core"
        base_core_hidden_size = config.base_scaffold.get_core_hidden_size(d_hidden)
        base_core_config = type(config.base_scaffold.core)(
            **{**config.base_scaffold.core.model_dump(), "hidden_size": base_core_hidden_size}
        )
        base_core = build_core(base_core_config)

        super().__init__(d_hidden=d_hidden, core=base_core)
        self.config = config

        self.wrapped_scaffold = build_scaffold(config=config.base_scaffold, d_hidden=d_hidden, core=base_core)

        # Adapter components
        self.ln = nn.LayerNorm(d_hidden)
        self.down = nn.Linear(d_hidden, config.bottleneck, bias=True)
        self.up = nn.Linear(config.bottleneck, d_hidden, bias=True)
        self.dropout = nn.Dropout(config.dropout) if config.dropout > 0 else nn.Identity()

        # Activation
        if config.activation == "gelu":
            self.act = nn.GELU()
        elif config.activation == "silu":
            self.act = nn.SiLU()
        else:
            self.act = nn.ReLU()

        # Gate starts at 0 => exact identity mapping at init
        if config.per_channel_gate:
            self.gate = nn.Parameter(torch.zeros(d_hidden))
        else:
            self.gate = nn.Parameter(torch.zeros(()))  # scalar

        # Identity-friendly init: zero weights on the up projection
        nn.init.zeros_(self.up.weight)
        nn.init.zeros_(self.up.bias)
        nn.init.kaiming_uniform_(self.down.weight, a=math.sqrt(5))
        nn.init.zeros_(self.down.bias)

    def init_state(self, batch: int, *, device: torch.device | str, dtype: torch.dtype) -> TensorDict:
        """Initialize state by delegating to the wrapped scaffold."""
        wrapped_state = self.wrapped_scaffold.init_state(batch=batch, device=device, dtype=dtype)
        return TensorDict({"wrapped": wrapped_state}, batch_size=[batch])

    def reset_state(self, state: MaybeState, mask: ResetMask) -> MaybeState:
        """Reset state by delegating to the wrapped scaffold."""
        if state is None:
            return None
        wrapped_state = state.get("wrapped", None)
        new_wrapped_state = self.wrapped_scaffold.reset_state(wrapped_state, mask)
        if new_wrapped_state is None:
            return None
        batch_size = state.batch_size[0] if state.batch_size else (mask.shape[0] if mask is not None else 1)
        return TensorDict({"wrapped": new_wrapped_state}, batch_size=[batch_size])

    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: Optional[ResetMask] = None,
    ) -> Tuple[Tensor, MaybeState]:
        wrapped_state = state.get("wrapped") if state is not None else None

        y, new_wrapped_state = self.wrapped_scaffold(x, wrapped_state, resets=resets)

        # Apply adapter residual (identity at init)
        adapter_out = self.up(self.dropout(self.act(self.down(self.ln(y)))))

        # Apply gate (broadcasts scalar to match tensor shape)
        g = self.gate if self.gate.ndim > 0 else self.gate.expand_as(adapter_out)
        y_adapted = y + g * adapter_out

        # Get batch size for state
        batch_size = x.shape[0]
        return y_adapted, TensorDict({"wrapped": new_wrapped_state}, batch_size=[batch_size])


__all__ = ["AdapterScaffold"]
