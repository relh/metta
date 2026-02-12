from __future__ import annotations

import torch.nn as nn

from cortex.rl.feature_extractors.box_cnn import BoxCNNFeatureExtractor
from cortex.rl.feature_extractors.config import (
    BoxCNNFeatureExtractorConfig,
    FeatureExtractorConfig,
    TokenMLPFeatureExtractorConfig,
    TokenPerceiverFeatureExtractorConfig,
)
from cortex.rl.feature_extractors.token_mlp import TokenMLPFeatureExtractor
from cortex.rl.feature_extractors.token_perceiver import TokenPerceiverFeatureExtractor


def build_feature_extractor(
    config: FeatureExtractorConfig,
    *,
    in_channels: int | None = None,
    input_hw: tuple[int, int] | None = None,
) -> nn.Module:
    if isinstance(config, TokenPerceiverFeatureExtractorConfig):
        return TokenPerceiverFeatureExtractor(config)
    if isinstance(config, TokenMLPFeatureExtractorConfig):
        return TokenMLPFeatureExtractor(config)
    if not isinstance(config, BoxCNNFeatureExtractorConfig):
        raise TypeError(f"Unsupported feature extractor config type: {type(config)!r}")

    if in_channels is None:
        raise ValueError("in_channels is required for box_cnn extractor")
    if input_hw is None:
        raise ValueError("input_hw is required for box_cnn extractor")
    return BoxCNNFeatureExtractor(config, in_channels=in_channels, input_hw=input_hw)


__all__ = ["build_feature_extractor"]
