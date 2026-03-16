"""Causal convolutional layers for Cortex cores."""

from __future__ import annotations

from typing import Optional, Tuple

import torch
import torch.nn as nn
from tensordict import TensorDict

from cortex.config import CausalConv1dCoreConfig
from cortex.cores.base import MemoryCore
from cortex.cores.registry import register_core
from cortex.kernels.dispatch import run_causal_conv1d
from cortex.types import MaybeState, ResetMask, Tensor


@register_core(CausalConv1dCoreConfig)
class CausalConv1dCore(MemoryCore):
    """Causal 1D convolution with depthwise or channel-mixing modes and stateful buffering."""

    def __init__(self, cfg: CausalConv1dCoreConfig) -> None:
        super().__init__(hidden_size=cfg.hidden_size)
        self.cfg = cfg

        # Determine grouping for convolution
        self.groups = cfg.hidden_size if not cfg.channel_mixing else 1

        if cfg.kernel_size == 0:
            self.conv = None  # No-op for kernel_size=0
        else:
            self.pad = cfg.kernel_size - 1  # Padding for temporal causality
            self.conv = nn.Conv1d(
                in_channels=cfg.hidden_size,
                out_channels=cfg.hidden_size,
                kernel_size=cfg.kernel_size,
                padding=self.pad,
                groups=self.groups,
                bias=cfg.causal_conv_bias,
            )

        self.reset_parameters()

    def reset_parameters(self):
        """Initialize convolution parameters."""
        if self.conv is not None:
            self.conv.reset_parameters()

    def init_state(self, batch: int, *, device: torch.device | str, dtype: torch.dtype) -> TensorDict:
        """Initialize convolution state buffer."""
        if self.cfg.kernel_size == 0:
            return TensorDict({}, batch_size=[batch])

        conv_state = torch.zeros(batch, self.cfg.kernel_size, self.cfg.hidden_size, device=device, dtype=dtype)
        return TensorDict({"conv": conv_state}, batch_size=[batch])

    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: Optional[ResetMask] = None,
    ) -> Tuple[Tensor, MaybeState]:
        """Apply causal convolution with optional resets."""
        # Handle both [B, F] and [B, T, F] inputs
        is_step = x.dim() == 2
        if is_step:
            x = x.unsqueeze(1)  # [B, F] -> [B, 1, F]

        B, T, F = x.shape

        # No-op for kernel_size=0
        if self.cfg.kernel_size == 0:
            if is_step:
                return x.squeeze(1), state
            return x, state

        # Initialize or get state
        if state is None or "conv" not in state:
            st = self.init_state(batch=B, device=x.device, dtype=x.dtype)
        else:
            st = state

        conv_state = st.get("conv")  # [B, KS, F]

        # Apply resets if provided
        if resets is not None and conv_state is not None:
            if is_step:
                mask = resets.to(dtype=x.dtype).view(B, 1, 1)
                conv_state = conv_state * (1.0 - mask)
            elif resets.dim() == 1:
                # Batch-level resets for sequences: reset at beginning
                mask = resets.to(dtype=x.dtype).view(B, 1, 1)
                conv_state = conv_state * (1.0 - mask)

        assert self.conv is not None  # kernel_size > 0 guaranteed by early return
        y, conv_state = run_causal_conv1d(
            x=x,
            conv_state=conv_state,
            weight=self.conv.weight,
            bias=self.conv.bias if self.cfg.causal_conv_bias else None,
            groups=self.groups,
            pad=self.pad,
            conv=self.conv,
            resets=resets,
            channel_mixing=self.cfg.channel_mixing,
        )

        new_state = TensorDict({"conv": conv_state}, batch_size=[B])
        if is_step:
            return y.squeeze(1), new_state
        return y, new_state

    def reset_state(self, state: MaybeState, mask: ResetMask) -> MaybeState:
        """Reset state for masked batch elements."""
        if state is None or "conv" not in state:
            return state

        mask_expanded = mask.to(dtype=state["conv"].dtype).view(-1, 1, 1)
        state["conv"] = state["conv"] * (1.0 - mask_expanded)
        return state


__all__ = ["CausalConv1dCore"]
