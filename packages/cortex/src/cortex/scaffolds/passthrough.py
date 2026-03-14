"""Passthrough scaffold that applies a core directly without projections."""

from __future__ import annotations

from typing import Optional, Tuple

from tensordict import TensorDict

from cortex.config import PassThroughScaffoldConfig
from cortex.cores.base import MemoryCore
from cortex.scaffolds.base import BaseScaffold
from cortex.scaffolds.registry import register_scaffold
from cortex.types import MaybeState, ResetMask, Tensor


@register_scaffold(PassThroughScaffoldConfig)
class PassThroughScaffold(BaseScaffold):
    """Applies the core directly, preserving external hidden size."""

    def __init__(self, config: PassThroughScaffoldConfig, d_hidden: int, core: MemoryCore) -> None:
        super().__init__(d_hidden=d_hidden, core=core)
        self.config = config
        assert core.hidden_size == d_hidden, "PassThroughScaffold requires core.hidden_size == d_hidden"

    def forward(
        self,
        x: Tensor,
        state: MaybeState,
        *,
        resets: Optional[ResetMask] = None,
    ) -> Tuple[Tensor, MaybeState]:
        core_key = self.core.__class__.__name__
        core_state = state.get(core_key, None) if state is not None else None
        batch_size = state.batch_size[0] if state is not None and state.batch_size else x.shape[0]

        y, new_core_state = self.core(x, core_state, resets=resets)

        return y, TensorDict({core_key: new_core_state}, batch_size=[batch_size])


__all__ = ["PassThroughScaffold"]
