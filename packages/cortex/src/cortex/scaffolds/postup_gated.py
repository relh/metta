"""Post-processing scaffold with GRU-style gating (GTrXL-inspired)."""

from __future__ import annotations

from typing import Optional, Tuple

import torch.nn as nn
from tensordict import TensorDict

from cortex.config import PostUpGatedScaffoldConfig
from cortex.consistent_dropout import ConsistentDropout
from cortex.cores.base import MemoryCore
from cortex.scaffolds.base import BaseScaffold
from cortex.scaffolds.gru_gating import GRUGatingUnit
from cortex.scaffolds.registry import register_scaffold
from cortex.types import MaybeState, ResetMask, Tensor


@register_scaffold(PostUpGatedScaffoldConfig)
class PostUpGatedScaffold(BaseScaffold):
    """Scaffold that applies a core then an FFN with GRU-style gated residuals."""

    def __init__(self, config: PostUpGatedScaffoldConfig, d_hidden: int, core: MemoryCore) -> None:
        super().__init__(d_hidden=d_hidden, core=core)
        self.config = config
        self.d_inner = int(config.proj_factor * d_hidden)
        assert core.hidden_size == d_hidden, "PostUpGatedScaffold requires core.hidden_size == d_hidden"

        self.norm1 = nn.LayerNorm(d_hidden, elementwise_affine=True, bias=False)
        self.norm2 = nn.LayerNorm(d_hidden, elementwise_affine=True, bias=False)

        # FFN with consistent dropout
        self.ffn_in = nn.Linear(d_hidden, self.d_inner)
        self.act = nn.SiLU()
        self.dropout = ConsistentDropout(config.dropout) if config.dropout > 0 else nn.Identity()
        self.ffn_out = nn.Linear(self.d_inner, d_hidden)

        # GRU-style gates (GTrXL-inspired)
        self.gate1 = GRUGatingUnit(d_hidden, bg=float(config.gru_bias))
        self.gate2 = GRUGatingUnit(d_hidden, bg=float(config.gru_bias))

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

        # Sublayer 1: core with pre-norm, then gated with residual x
        x1 = self.norm1(x)
        y_core, new_core_state = self.core(x1, core_state, resets=resets)
        y = self.gate1(x, y_core)

        # Sublayer 2: FFN with pre-norm on y, then gate with residual y
        y2 = self.norm2(y)
        is_step = y2.dim() == 2
        if is_step:
            ffn = self.ffn_in(y2)
            ffn = self.act(ffn)
            ffn = self.dropout(ffn)
            ffn = self.ffn_out(ffn)
        else:
            B, T, H = y2.shape
            ffn = self.ffn_in(y2.reshape(B * T, H))
            ffn = self.act(ffn)
            ffn = self.dropout(ffn)
            ffn = self.ffn_out(ffn).reshape(B, T, self.d_hidden)

        out = self.gate2(y, ffn)
        return out, TensorDict({core_key: new_core_state}, batch_size=[batch_size])


__all__ = ["PostUpGatedScaffold"]
