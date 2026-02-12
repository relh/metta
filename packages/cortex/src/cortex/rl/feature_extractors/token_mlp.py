from __future__ import annotations

import torch
import torch.nn as nn

from cortex.rl.feature_extractors.config import TokenMLPFeatureExtractorConfig
from cortex.rl.feature_extractors.token_embed import TokenFourierEmbedder


class TokenMLPFeatureExtractor(nn.Module):
    def __init__(self, config: TokenMLPFeatureExtractorConfig) -> None:
        super().__init__()
        self.config = config
        self._pool = config.pool
        self._use_mask = bool(config.use_mask)

        self.embedder = TokenFourierEmbedder(
            attr_embed_dim=config.attr_embed_dim,
            num_fourier_freqs=config.num_fourier_freqs,
            coord_max_value=config.coord_max_value,
        )

        dims = [self.embedder.feat_dim] + list(config.hidden_features) + [int(config.output_dim)]
        layers: list[nn.Module] = []
        for i, (in_features, out_features) in enumerate(zip(dims[:-1], dims[1:], strict=False)):
            layers.append(nn.Linear(in_features, out_features))
            if i < len(dims) - 2:
                layers.append(nn.GELU())
        self.network = nn.Sequential(*layers)

    def forward(self, observations: torch.Tensor, *, obs_mask: torch.Tensor | None = None) -> torch.Tensor:
        key_mask = None
        if self._use_mask and obs_mask is not None:
            key_mask = obs_mask if obs_mask.dtype == torch.bool else obs_mask.to(dtype=torch.bool)
        features = self.embedder(observations, obs_mask=key_mask if self._use_mask else None)

        if self._pool == "mean":
            pooled = self._masked_mean(features, key_mask)
        elif self._pool == "sum":
            pooled = self._masked_sum(features, key_mask)
        else:
            raise ValueError(f"Unsupported token MLP pool mode: {self._pool}")

        return self.network(pooled)

    def _masked_mean(self, features: torch.Tensor, mask: torch.Tensor | None) -> torch.Tensor:
        if mask is None:
            return features.mean(dim=1)
        valid = (~mask).to(features.dtype).unsqueeze(-1)
        denom = valid.sum(dim=1).clamp_min(1.0)
        return (features * valid).sum(dim=1) / denom

    def _masked_sum(self, features: torch.Tensor, mask: torch.Tensor | None) -> torch.Tensor:
        if mask is None:
            return features.sum(dim=1)
        valid = (~mask).to(features.dtype).unsqueeze(-1)
        return (features * valid).sum(dim=1)


__all__ = ["TokenMLPFeatureExtractor"]
