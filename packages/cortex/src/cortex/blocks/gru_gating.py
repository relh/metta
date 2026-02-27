"""GRU-style gating unit (GTrXL-inspired)."""

from __future__ import annotations

import torch
import torch.nn as nn

from cortex.types import Tensor


class GRUGatingUnit(nn.Module):
    """GRU-style gating unit mixing residual and sublayer outputs (GTrXL-style)."""

    def __init__(self, hidden_size: int, bg: float = 2.0) -> None:
        super().__init__()
        H = hidden_size
        self.Wr = nn.Linear(H, H, bias=False)
        self.Ur = nn.Linear(H, H, bias=False)
        self.Wz = nn.Linear(H, H, bias=False)
        self.Uz = nn.Linear(H, H, bias=False)
        self.Wg = nn.Linear(H, H, bias=False)
        self.Ug = nn.Linear(H, H, bias=False)
        self.bg = nn.Parameter(torch.full((H,), bg))
        self.sigmoid = nn.Sigmoid()
        self.tanh = nn.Tanh()

    def forward(self, x: Tensor, y: Tensor) -> Tensor:
        r = self.sigmoid(self.Wr(y) + self.Ur(x))
        z = self.sigmoid(self.Wz(y) + self.Uz(x) - self.bg)
        h = self.tanh(self.Wg(y) + self.Ug(r * x))
        return (1 - z) * x + z * h


__all__ = ["GRUGatingUnit"]
