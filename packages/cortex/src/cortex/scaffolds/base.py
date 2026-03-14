"""Base abstract scaffold interface for wrapping memory cores."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

import torch
import torch.nn as nn
from tensordict import TensorDict

from cortex.cores.base import MemoryCore
from cortex.types import MaybeState, ResetMask, Tensor


class BaseScaffold(nn.Module, ABC):
    """Abstract scaffold wrapping a memory core with optional projections."""

    def __init__(self, d_hidden: int, core: MemoryCore) -> None:
        super().__init__()
        self.d_hidden = d_hidden
        self.core = core

    def init_state(self, batch: int, *, device: torch.device | str, dtype: torch.dtype) -> TensorDict:
        core_state = self.core.init_state(batch=batch, device=device, dtype=dtype)
        core_key = self.core.__class__.__name__
        return TensorDict({core_key: core_state}, batch_size=[batch])

    def reset_state(self, state: MaybeState, mask: ResetMask) -> MaybeState:
        if state is None:
            return None
        core_key = self.core.__class__.__name__
        core_state = state.get(core_key, None)
        new_core_state = self.core.reset_state(core_state, mask)
        if new_core_state is None:
            return None
        batch_size = (
            state.batch_size[0]
            if state.batch_size
            else (new_core_state.batch_size[0] if new_core_state.batch_size else mask.shape[0])
        )
        return TensorDict({core_key: new_core_state}, batch_size=[batch_size])

    @abstractmethod
    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: Optional[ResetMask] = None,
    ) -> Tuple[Tensor, MaybeState]: ...


__all__ = ["BaseScaffold"]
