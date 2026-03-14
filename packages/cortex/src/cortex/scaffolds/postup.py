"""Post-processing scaffold that applies a core then an FFN with residual connections."""

from __future__ import annotations

from typing import Optional, Tuple

import torch.nn as nn
from tensordict import TensorDict

from cortex.config import PostUpScaffoldConfig
from cortex.consistent_dropout import ConsistentDropout
from cortex.cores.base import MemoryCore
from cortex.scaffolds.base import BaseScaffold
from cortex.scaffolds.registry import register_scaffold
from cortex.types import MaybeState, ResetMask, Tensor


@register_scaffold(PostUpScaffoldConfig)
class PostUpScaffold(BaseScaffold):
    """Scaffold that applies a core then an FFN sublayer with residual connections."""

    def __init__(self, config: PostUpScaffoldConfig, d_hidden: int, core: MemoryCore) -> None:
        super().__init__(d_hidden=d_hidden, core=core)
        self.config = config
        self.d_inner = int(config.proj_factor * d_hidden)
        assert core.hidden_size == d_hidden, "PostUpScaffold requires core.hidden_size == d_hidden"
        self.norm = nn.LayerNorm(d_hidden, elementwise_affine=True, bias=False)
        self.ffn_norm = nn.LayerNorm(d_hidden, elementwise_affine=True, bias=False)
        self.out1 = nn.Linear(d_hidden, self.d_inner)
        self.act = nn.SiLU()
        self.dropout = ConsistentDropout(config.dropout) if config.dropout > 0 else nn.Identity()
        self.out2 = nn.Linear(self.d_inner, d_hidden)

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

        residual = x
        x_normed = self.norm(x)
        y_core, new_core_state = self.core(x_normed, core_state, resets=resets)
        y = residual + y_core

        ffn_residual = y
        y_ffn_normed = self.ffn_norm(y)
        is_step = y_ffn_normed.dim() == 2
        if is_step:
            y_ffn = self.out1(y_ffn_normed)
            y_ffn = self.act(y_ffn)
            y_ffn = self.dropout(y_ffn)
            y_ffn = self.out2(y_ffn)
        else:
            B, T, H = y_ffn_normed.shape
            y_ = self.out1(y_ffn_normed.reshape(B * T, H))
            y_ = self.act(y_)
            y_ = self.dropout(y_)
            y_ffn = self.out2(y_).reshape(B, T, self.d_hidden)

        y = ffn_residual + y_ffn
        return y, TensorDict({core_key: new_core_state}, batch_size=[batch_size])


__all__ = ["PostUpScaffold"]
