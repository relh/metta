from __future__ import annotations

import importlib
import importlib.util
from typing import Any, cast

import einops
import torch
import torch.nn as nn
import torch.nn.functional as F

from cortex.rl.feature_extractors.config import TokenPerceiverFeatureExtractorConfig
from cortex.rl.feature_extractors.token_embed import TokenFourierEmbedder

try:
    _xops_spec = importlib.util.find_spec("xformers.ops")
except (ImportError, ModuleNotFoundError):
    _xops_spec = None

if _xops_spec is not None:
    try:
        xops: Any | None = importlib.import_module("xformers.ops")
    except (ImportError, ModuleNotFoundError):
        xops = None
else:
    xops = None


class TokenPerceiverFeatureExtractor(nn.Module):
    def __init__(self, config: TokenPerceiverFeatureExtractorConfig) -> None:
        super().__init__()
        self.config = config
        self._latent_dim = int(config.latent_dim)
        self._num_latents = int(config.num_latents)
        self._num_heads = int(config.num_heads)
        self._num_layers = int(config.num_layers)
        self._mlp_ratio = float(config.mlp_ratio)
        self._use_mask = bool(config.use_mask)
        self._pool = config.pool

        self.embedder = TokenFourierEmbedder(
            attr_embed_dim=config.attr_embed_dim,
            num_fourier_freqs=config.num_fourier_freqs,
            coord_max_value=config.coord_max_value,
        )
        self._feat_dim = self.embedder.feat_dim

        if self._latent_dim % self._num_heads != 0:
            raise ValueError("latent_dim must be divisible by num_heads")

        self.latents = nn.Parameter(torch.randn(1, self._num_latents, self._latent_dim))
        nn.init.trunc_normal_(self.latents, std=0.02)

        self.token_norm = nn.LayerNorm(self._feat_dim)
        self.kv_proj = nn.Linear(self._feat_dim, 2 * self._latent_dim, bias=False)

        self.layers = nn.ModuleList([])
        for _ in range(self._num_layers):
            self.layers.append(
                nn.ModuleDict(
                    {
                        "latent_norm": nn.LayerNorm(self._latent_dim),
                        "q_proj": nn.Linear(self._latent_dim, self._latent_dim, bias=False),
                        "attn_out_proj": nn.Linear(self._latent_dim, self._latent_dim),
                        "mlp_norm": nn.LayerNorm(self._latent_dim),
                        "mlp": nn.Sequential(
                            nn.Linear(self._latent_dim, int(self._latent_dim * self._mlp_ratio)),
                            nn.GELU(),
                            nn.Linear(int(self._latent_dim * self._mlp_ratio), self._latent_dim),
                        ),
                    }
                )
            )

        self.final_norm = nn.LayerNorm(self._latent_dim)
        self._xops: Any | None = xops

    def forward(self, observations: torch.Tensor, *, obs_mask: torch.Tensor | None = None) -> torch.Tensor:
        key_mask = None
        if self._use_mask and obs_mask is not None:
            key_mask = obs_mask if obs_mask.dtype == torch.bool else obs_mask.to(dtype=torch.bool)
        x_features = self.embedder(observations, obs_mask=key_mask if self._use_mask else None)

        tokens_norm = self.token_norm(x_features)
        kv = self.kv_proj(tokens_norm)
        k, v = kv.split(self._latent_dim, dim=-1)
        k = einops.rearrange(k, "b m (h d) -> b h m d", h=self._num_heads)
        v = einops.rearrange(v, "b m (h d) -> b h m d", h=self._num_heads)

        use_xops, k_x, v_x, xops_attn_bias, attn_mask = self._prepare_attention_inputs(
            k=k,
            v=v,
            key_mask=key_mask,
        )

        latents = self.latents.expand(x_features.shape[0], -1, -1)

        for raw_layer in self.layers:
            layer = cast(nn.ModuleDict, raw_layer)

            residual = latents
            q = layer["q_proj"](layer["latent_norm"](latents))
            q = einops.rearrange(q, "b n (h d) -> b h n d", h=self._num_heads)

            if use_xops:
                assert k_x is not None and v_x is not None
                q_x = q.permute(0, 2, 1, 3)
                attn_output = cast(Any, self._xops).memory_efficient_attention(
                    q_x,
                    k_x,
                    v_x,
                    attn_bias=xops_attn_bias,
                    p=0.0,
                )
                attn_output = attn_output.permute(0, 2, 1, 3)
            else:
                attn_output = self._scaled_dot_product_attention(q=q, k=k, v=v, attn_mask=attn_mask)
            attn_output = einops.rearrange(attn_output, "b h n d -> b n (h d)")
            latents = residual + layer["attn_out_proj"](attn_output)

            latents = latents + layer["mlp"](layer["mlp_norm"](latents))

        latents = self.final_norm(latents)

        if self._pool == "mean":
            return latents.mean(dim=1)
        if self._pool == "first":
            return latents[:, 0]
        if self._pool == "none":
            return einops.rearrange(latents, "b n d -> b (n d)")
        raise ValueError("unsupported pool mode")

    def _prepare_attention_inputs(
        self,
        *,
        k: torch.Tensor,
        v: torch.Tensor,
        key_mask: torch.Tensor | None,
    ) -> tuple[bool, torch.Tensor | None, torch.Tensor | None, Any | None, torch.Tensor | None]:
        xops = self._xops
        use_xops = k.is_cuda and xops is not None
        xops_attn_bias = None
        if use_xops and key_mask is not None:
            padding_mask = getattr(cast(Any, xops).fmha.attn_bias, "PaddingMask", None)
            if padding_mask is None:
                use_xops = False
            else:
                xops_attn_bias = padding_mask(key_mask)

        if use_xops:
            k_x = k.permute(0, 2, 1, 3)
            v_x = v.permute(0, 2, 1, 3)
            return True, k_x, v_x, xops_attn_bias, None

        attn_mask = None
        if key_mask is not None:
            attn_mask = key_mask[:, None, None, :]
        return False, None, None, None, attn_mask

    @staticmethod
    def _scaled_dot_product_attention(
        *,
        q: torch.Tensor,
        k: torch.Tensor,
        v: torch.Tensor,
        attn_mask: torch.Tensor | None,
    ) -> torch.Tensor:
        if q.is_cuda:
            with torch.backends.cuda.sdp_kernel(enable_flash=True, enable_mem_efficient=True, enable_math=True):
                return F.scaled_dot_product_attention(q, k, v, attn_mask=attn_mask)
        return F.scaled_dot_product_attention(q, k, v, attn_mask=attn_mask)


__all__ = ["TokenPerceiverFeatureExtractor"]
