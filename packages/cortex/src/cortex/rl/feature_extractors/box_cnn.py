from __future__ import annotations

import math
from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from cortex.rl.feature_extractors.config import BoxCNNFeatureExtractorConfig


class BoxCNNFeatureExtractor(nn.Module):
    def __init__(self, config: BoxCNNFeatureExtractorConfig, *, in_channels: int, input_hw: tuple[int, int]) -> None:
        super().__init__()
        self.config = config

        self.cnn1 = nn.Conv2d(
            in_channels,
            int(config.conv1_out_channels),
            kernel_size=int(config.conv1_kernel_size),
            stride=int(config.conv1_stride),
            padding=int(config.conv1_padding),
        )
        self.cnn2 = nn.Conv2d(
            int(config.conv1_out_channels),
            int(config.conv2_out_channels),
            kernel_size=int(config.conv2_kernel_size),
            stride=int(config.conv2_stride),
            padding=int(config.conv2_padding),
        )

        flattened_size = self._compute_flattened_size(input_hw)
        self.fc1 = nn.Linear(flattened_size, int(config.hidden_dim))
        self.self_encoder = nn.Linear(in_channels, int(config.hidden_dim))
        self.out = nn.Linear(int(config.hidden_dim) * 2, int(config.output_dim))

    def _compute_flattened_size(self, input_hw: tuple[int, int]) -> int:
        conv1_hw = self._conv2d_output_shape(
            input_hw,
            self.config.conv1_kernel_size,
            self.config.conv1_stride,
            self.config.conv1_padding,
        )
        conv2_hw = self._conv2d_output_shape(
            conv1_hw,
            self.config.conv2_kernel_size,
            self.config.conv2_stride,
            self.config.conv2_padding,
        )
        flattened = int(self.config.conv2_out_channels) * conv2_hw[0] * conv2_hw[1]
        if flattened <= 0:
            raise ValueError("Computed flattened size for box CNN extractor is non-positive")
        return flattened

    @staticmethod
    def _conv2d_output_shape(
        input_hw: Tuple[int, int],
        kernel_size: int,
        stride: int,
        padding: int = 0,
        dilation: int = 1,
    ) -> Tuple[int, int]:
        h, w = input_hw

        def _single(out_size: int, k: int, s: int, p: int, d: int) -> int:
            return math.floor((out_size + 2 * p - d * (k - 1) - 1) / s + 1)

        return (
            _single(h, int(kernel_size), int(stride), int(padding), int(dilation)),
            _single(w, int(kernel_size), int(stride), int(padding), int(dilation)),
        )

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.cnn1(observations))
        x = F.relu(self.cnn2(x))
        x = torch.flatten(x, start_dim=1)
        cnn_features = F.relu(self.fc1(x))

        _, _, h, w = observations.shape
        center_features = observations[:, :, h // 2, w // 2]
        self_features = F.relu(self.self_encoder(center_features))

        return self.out(torch.cat([cnn_features, self_features], dim=-1))


__all__ = ["BoxCNNFeatureExtractor"]
