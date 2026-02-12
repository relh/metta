from __future__ import annotations

import torch
import torch.nn as nn


def _coordinates_from_obs_tokens(observations: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    coords_byte = observations[..., 0].to(torch.long)
    y_coords = (coords_byte >> 4) & 0x0F
    x_coords = coords_byte & 0x0F
    return x_coords, y_coords


class TokenFourierEmbedder(nn.Module):
    def __init__(self, *, attr_embed_dim: int, num_fourier_freqs: int, coord_max_value: float) -> None:
        super().__init__()
        self._attr_embed_dim = int(attr_embed_dim)
        self._num_fourier_freqs = int(num_fourier_freqs)
        self._coord_rep_dim = 4 * self._num_fourier_freqs
        self._feat_dim = self._attr_embed_dim + self._coord_rep_dim + 1
        self._coord_max_value = float(coord_max_value)

        self._attr_embeds = nn.Embedding(256, self._attr_embed_dim, padding_idx=255)
        nn.init.trunc_normal_(self._attr_embeds.weight, std=0.02)
        self.register_buffer("frequencies", 2.0 ** torch.arange(self._num_fourier_freqs))

    @property
    def feat_dim(self) -> int:
        return self._feat_dim

    def forward(self, observations: torch.Tensor, *, obs_mask: torch.Tensor | None = None) -> torch.Tensor:
        attr_indices = observations[..., 1].long()
        attr_embeds = self._attr_embeds(attr_indices)

        feat_vectors = torch.empty(
            (*attr_embeds.shape[:-1], self._feat_dim),
            dtype=attr_embeds.dtype,
            device=attr_embeds.device,
        )
        feat_vectors[..., : self._attr_embed_dim] = attr_embeds

        x_coord_indices, y_coord_indices = _coordinates_from_obs_tokens(observations)
        x_coords_norm = x_coord_indices.to(torch.float32) / self._coord_max_value * 2.0 - 1.0
        y_coords_norm = y_coord_indices.to(torch.float32) / self._coord_max_value * 2.0 - 1.0

        x_coords_norm = x_coords_norm.unsqueeze(-1)
        y_coords_norm = y_coords_norm.unsqueeze(-1)
        frequencies = self.get_buffer("frequencies").view(*([1] * (x_coords_norm.dim() - 1)), -1)

        x_scaled = x_coords_norm * frequencies
        y_scaled = y_coords_norm * frequencies

        offset = self._attr_embed_dim
        feat_vectors[..., offset : offset + self._num_fourier_freqs] = torch.cos(x_scaled)
        offset += self._num_fourier_freqs
        feat_vectors[..., offset : offset + self._num_fourier_freqs] = torch.sin(x_scaled)
        offset += self._num_fourier_freqs
        feat_vectors[..., offset : offset + self._num_fourier_freqs] = torch.cos(y_scaled)
        offset += self._num_fourier_freqs
        feat_vectors[..., offset : offset + self._num_fourier_freqs] = torch.sin(y_scaled)

        feat_vectors[..., self._attr_embed_dim + self._coord_rep_dim :] = observations[..., 2].float().unsqueeze(-1)

        if obs_mask is not None:
            mask = obs_mask if obs_mask.dtype == torch.bool else obs_mask.to(dtype=torch.bool)
            feat_vectors = feat_vectors.masked_fill(mask.unsqueeze(-1), 0.0)

        return feat_vectors


__all__ = ["TokenFourierEmbedder"]
