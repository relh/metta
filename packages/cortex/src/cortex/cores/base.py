"""Abstract interface for memory cores with explicit TensorDict state management."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

import torch
import torch.nn as nn
from tensordict import TensorDict

from cortex.types import MaybeState, ResetMask, Tensor


class MemoryCore(nn.Module, ABC):
    """Abstract memory core interface with explicit TensorDict state passing."""

    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.hidden_size = hidden_size

    @abstractmethod
    def init_state(self, batch: int, *, device: torch.device | str, dtype: torch.dtype) -> TensorDict:
        """Initialize zero state for the given batch size."""

    @abstractmethod
    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: Optional[ResetMask] = None,
    ) -> Tuple[Tensor, MaybeState]:
        """Process input with current state and optional resets."""

    @abstractmethod
    def reset_state(self, state: MaybeState, mask: ResetMask) -> MaybeState:
        """Apply a reset mask to zero selected batch elements."""


__all__ = ["MemoryCore"]
