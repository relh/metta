"""Consistent Dropout for Policy Gradient RL.

Implementation of "Consistent Dropout for Policy Gradient Reinforcement Learning"
(Hausknecht & Wagener, 2022) - https://arxiv.org/abs/2202.11818

The key insight is that naive dropout in policy gradient methods causes training
instability because different dropout masks are used during rollout vs training.
Consistent dropout caches the dropout mask during rollout and reuses it during
the training update phase, reducing gradient variance.

Usage:
    dropout = ConsistentDropout(p=0.1)

    # During rollout - generates and caches mask
    dropout.reset_mask()  # Clear any previous mask
    out = dropout(x)       # Generates new mask and caches it

    # During training - reuses cached mask
    out = dropout(x)       # Uses the same mask from rollout

    # The mask is automatically reset when calling reset_mask()
"""

from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn
from torch import Tensor


class ConsistentDropout(nn.Module):
    """Dropout that caches masks for consistency between rollout and training.

    Unlike standard dropout which generates new masks on every forward pass,
    ConsistentDropout caches the mask after first use and reuses it until
    explicitly reset. This is critical for stable policy gradient training.

    The mask is stored per input shape and automatically regenerated when:
    - reset_mask() is called
    - Input shape changes
    - Module is in eval mode (dropout disabled)

    Attributes:
        p: Dropout probability (0 = no dropout, 1 = all zeros)
        inplace: Whether to modify input in place (not recommended with caching)
    """

    def __init__(self, p: float = 0.5, inplace: bool = False) -> None:
        """Initialize ConsistentDropout.

        Args:
            p: Dropout probability between 0 and 1
            inplace: If True, modify input in place (default False)
        """
        super().__init__()
        if p < 0 or p > 1:
            raise ValueError(f"dropout probability has to be between 0 and 1, but got {p}")
        self.p = p
        self.inplace = inplace
        self._cached_mask: Optional[Tensor] = None
        self._cached_shape: Optional[tuple[int, ...]] = None

    def reset_mask(self) -> None:
        """Clear the cached dropout mask.

        Call this at the start of each rollout to generate fresh masks.
        The next forward pass will create a new mask.
        """
        self._cached_mask = None
        self._cached_shape = None

    def _generate_mask(self, x: Tensor) -> Tensor:
        """Generate a new dropout mask for the given input.

        Args:
            x: Input tensor to generate mask for

        Returns:
            Binary mask tensor scaled by 1/(1-p) for expectation preservation
        """
        if self.p == 0:
            return torch.ones_like(x)
        if self.p == 1:
            return torch.zeros_like(x)

        # Generate Bernoulli mask and scale to preserve expected value
        mask = torch.empty_like(x).bernoulli_(1 - self.p)
        mask = mask / (1 - self.p)
        return mask

    def _expand_mask(self, current_shape: tuple[int, ...], device: torch.device) -> Optional[Tensor]:
        """Expand cached mask for compatible reshaped batches.

        This handles the common training case where rollout uses [B, H] but
        training flattens to [B*TT, H]. We repeat the cached mask across the
        time dimension so the same per-batch mask is reused.
        """
        if self._cached_mask is None or self._cached_shape is None:
            return None
        if self._cached_mask.device != device:
            return None
        if len(self._cached_shape) != 2 or len(current_shape) != 2:
            return None
        cached_batch, cached_feat = self._cached_shape
        current_batch, current_feat = current_shape
        if cached_feat != current_feat:
            return None
        if cached_batch <= 0 or current_batch % cached_batch != 0:
            return None
        repeat = current_batch // cached_batch
        if repeat <= 1:
            return None
        return self._cached_mask.repeat_interleave(repeat, dim=0)

    def forward(self, x: Tensor) -> Tensor:
        """Apply consistent dropout to input.

        During training:
        - If no cached mask exists, generates and caches a new one
        - If cached mask exists with matching shape, reuses it
        - If shape changed, generates new mask

        During eval:
        - Returns input unchanged (standard dropout behavior)

        Args:
            x: Input tensor

        Returns:
            Tensor with dropout applied
        """
        if not self.training or self.p == 0:
            return x

        current_shape = tuple(x.shape)

        # Check if we need a new mask
        need_new_mask = (
            self._cached_mask is None or self._cached_shape != current_shape or self._cached_mask.device != x.device
        )
        if need_new_mask:
            expanded = self._expand_mask(current_shape, x.device)
            if expanded is not None:
                self._cached_mask = expanded
                self._cached_shape = current_shape
                need_new_mask = False

        if need_new_mask:
            self._cached_mask = self._generate_mask(x)
            self._cached_shape = current_shape

        if self.inplace:
            return x.mul_(self._cached_mask)
        return x * self._cached_mask

    def extra_repr(self) -> str:
        return f"p={self.p}, inplace={self.inplace}"


class ConsistentDropoutModule(nn.Module):
    """Convenience wrapper that applies ConsistentDropout to a wrapped module.

    This is useful for adding consistent dropout to existing layers without
    modifying their forward methods.

    Example:
        # Wrap a linear layer with dropout
        layer = ConsistentDropoutModule(nn.Linear(256, 128), p=0.1)
    """

    def __init__(self, module: nn.Module, p: float = 0.5) -> None:
        """Initialize wrapper.

        Args:
            module: Module to wrap with dropout
            p: Dropout probability
        """
        super().__init__()
        self.module = module
        self.dropout = ConsistentDropout(p=p)

    def reset_mask(self) -> None:
        """Reset the dropout mask."""
        self.dropout.reset_mask()

    def forward(self, x: Tensor) -> Tensor:
        """Apply module then dropout."""
        return self.dropout(self.module(x))


def reset_consistent_dropout(module: nn.Module) -> None:
    """Recursively reset all ConsistentDropout masks in a module.

    Call this at the start of each rollout to ensure fresh masks.

    Args:
        module: Root module to search for ConsistentDropout layers
    """
    for m in module.modules():
        if isinstance(m, ConsistentDropout):
            m.reset_mask()


__all__ = [
    "ConsistentDropout",
    "ConsistentDropoutModule",
    "reset_consistent_dropout",
]
