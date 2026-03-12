"""Router modules: global prior router and per-token refiner for Column experts."""

from __future__ import annotations

import math
from typing import Optional

import torch
import torch.nn as nn

from cortex.config import RouterConfig
from cortex.routed_adapter import get_route_ids
from cortex.types import Tensor


class BaseRouter(nn.Module):
    """Abstract router that returns a global expert gate via forward()."""

    def forward(self, expert_outputs: Optional[list[Tensor]] = None) -> Tensor:  # shape: [K] or [B, K]
        raise NotImplementedError


class GlobalContextRouter(BaseRouter):
    """Global context · expert keys with softmax gating."""

    def __init__(self, d_hidden: int, num_experts: int, cfg: RouterConfig) -> None:
        super().__init__()
        d_key = int(cfg.d_key or d_hidden)
        self.d_key = d_key
        self.temperature = float(cfg.temperature)
        self.top_k = int(cfg.top_k) if cfg.top_k is not None else None
        self.use_sqrt_scale = bool(cfg.use_sqrt_scale)

        self.context = nn.Parameter(torch.zeros(d_hidden))
        self.keys = nn.Parameter(torch.zeros(num_experts, d_key))
        self.Wq = nn.Linear(d_hidden, d_key, bias=False)
        self.Wk = nn.Linear(d_key, d_key, bias=False)

        nn.init.uniform_(self.context, a=-1e-3, b=1e-3)
        nn.init.uniform_(self.keys, a=-1e-3, b=1e-3)
        nn.init.uniform_(self.Wq.weight, a=-cfg.init_scale_wq, b=cfg.init_scale_wq)
        nn.init.uniform_(self.Wk.weight, a=-cfg.init_scale_wk, b=cfg.init_scale_wk)

    @torch.no_grad()
    def _topk_mask(self, scores: Tensor) -> Tensor:
        if self.top_k is None:
            return scores
        k = int(self.top_k)
        if scores.dim() == 1:
            if k >= scores.shape[0]:
                return scores
            topk_vals, topk_idx = torch.topk(scores, k)
            masked = torch.full_like(scores, float("-inf"))
            masked[topk_idx] = topk_vals
            return masked
        if scores.dim() == 2:
            if k >= scores.shape[-1]:
                return scores
            topk_vals, topk_idx = torch.topk(scores, k, dim=-1)
            masked = torch.full_like(scores, float("-inf"))
            masked.scatter_(dim=-1, index=topk_idx, src=topk_vals)
            return masked
        raise ValueError(f"Expected scores with dim 1 or 2, got shape {tuple(scores.shape)}")

    def _global_scores(self) -> Tensor:
        """Unnormalized global scores over experts (before temperature and softmax)."""
        scale = 1.0 / math.sqrt(self.d_key) if self.use_sqrt_scale else 1.0 / float(self.d_key)
        route_ids = get_route_ids()
        if route_ids is None:
            q = self.Wq(self.context)  # [d_k]
            k_proj = self.Wk(self.keys)  # [E, d_k]
            return torch.einsum("kd,d->k", k_proj, q) * scale  # [E]

        batch_size = int(route_ids.shape[0])
        q_in = self.context.unsqueeze(0).expand(batch_size, -1)  # [B, d_hidden]
        k_in = self.keys.unsqueeze(0).expand(batch_size, -1, -1)  # [B, E, d_k]
        q = self.Wq(q_in)  # [B, d_k]
        k_proj = self.Wk(k_in)  # [B, E, d_k]
        return torch.einsum("bed,bd->be", k_proj, q) * scale  # [B, E]

    def global_logits(self, *, restrict_topk: bool = True) -> Tensor:
        scores = self._global_scores()
        if restrict_topk and self.top_k is not None:
            with torch.no_grad():
                scores = self._topk_mask(scores)
        logits = scores / max(self.temperature, 1e-6)
        return logits

    def forward(self, expert_outputs: Optional[list[Tensor]] = None) -> Tensor:
        """Return the global gate; expert_outputs is ignored for backward-compat."""
        logits = self.global_logits(restrict_topk=True)
        gate = torch.softmax(logits, dim=-1)
        return gate


class TokenRefiner(nn.Module):
    """Compute centered per‑token refinement logits from tokens for expert gating."""

    def __init__(self, d_hidden: int, num_experts: int, cfg: RouterConfig) -> None:
        super().__init__()
        self.num_experts = int(num_experts)
        d_key_local = int(getattr(cfg, "d_key_local", None) or getattr(cfg, "d_key", None) or d_hidden)
        self.d_key_local = d_key_local
        self.local_temperature = float(getattr(cfg, "local_temperature", 1.0))
        self.center_refine = bool(getattr(cfg, "center_refine", True))

        self.Wq_tok = nn.Linear(d_hidden, d_key_local, bias=False)
        self.k_loc = nn.Parameter(torch.zeros(num_experts, d_key_local))

        nn.init.uniform_(self.Wq_tok.weight, a=-1e-3, b=1e-3)
        nn.init.uniform_(self.k_loc, a=-1e-3, b=1e-3)

    def forward(self, x_tokens: Tensor) -> Tensor:
        """Return centered refinement logits p̂_t with shape [B,T,E] (or [B,1,E] for step)."""
        tau = max(self.local_temperature, 1e-6)
        if x_tokens.dim() == 2:
            x_tokens = x_tokens.unsqueeze(1)  # [B,1,H]
        q = self.Wq_tok(x_tokens)  # [B,T,d_k_loc]
        p = torch.einsum("btd,ed->bte", q, self.k_loc)  # [B,T,E]
        p = p / (tau * math.sqrt(self.d_key_local))
        if self.center_refine:
            p = p - p.mean(dim=-1, keepdim=True)
        return p


__all__ = ["BaseRouter", "GlobalContextRouter", "TokenRefiner"]
