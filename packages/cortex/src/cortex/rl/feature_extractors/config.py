from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class TokenPerceiverFeatureExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["token_perceiver"] = "token_perceiver"
    attr_embed_dim: int = Field(default=8, ge=1)
    num_fourier_freqs: int = Field(default=3, ge=1)
    latent_dim: int = Field(default=128, ge=1)
    num_latents: int = Field(default=12, ge=1)
    num_heads: int = Field(default=4, ge=1)
    num_layers: int = Field(default=2, ge=1)
    mlp_ratio: float = Field(default=4.0, gt=0.0)
    use_mask: bool = True
    pool: Literal["mean", "first", "none"] = "mean"
    coord_max_value: float = Field(default=10.0, gt=0.0)
    max_tokens: int | None = Field(default=128, ge=1)
    ignore_inventory_power_tokens: bool = True


class TokenMLPFeatureExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["token_mlp"] = "token_mlp"
    attr_embed_dim: int = Field(default=8, ge=1)
    num_fourier_freqs: int = Field(default=3, ge=1)
    hidden_features: list[int] = Field(default_factory=lambda: [128])
    output_dim: int = Field(default=128, ge=1)
    use_mask: bool = True
    pool: Literal["mean", "sum"] = "mean"
    coord_max_value: float = Field(default=10.0, gt=0.0)
    max_tokens: int | None = Field(default=128, ge=1)
    ignore_inventory_power_tokens: bool = True


class BoxCNNFeatureExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["box_cnn"] = "box_cnn"
    conv1_out_channels: int = Field(default=64, ge=1)
    conv1_kernel_size: int = Field(default=3, ge=1)
    conv1_stride: int = Field(default=2, ge=1)
    conv1_padding: int = Field(default=1, ge=0)
    conv2_out_channels: int = Field(default=128, ge=1)
    conv2_kernel_size: int = Field(default=3, ge=1)
    conv2_stride: int = Field(default=2, ge=1)
    conv2_padding: int = Field(default=1, ge=0)
    hidden_dim: int = Field(default=256, ge=1)
    output_dim: int = Field(default=128, ge=1)


FeatureExtractorConfig = Annotated[
    Union[
        TokenPerceiverFeatureExtractorConfig,
        TokenMLPFeatureExtractorConfig,
        BoxCNNFeatureExtractorConfig,
    ],
    Field(discriminator="type"),
]


def feature_extractor_output_dim(config: FeatureExtractorConfig) -> int:
    if isinstance(config, TokenPerceiverFeatureExtractorConfig):
        if config.pool == "none":
            return int(config.num_latents * config.latent_dim)
        return int(config.latent_dim)
    if isinstance(config, TokenMLPFeatureExtractorConfig):
        return int(config.output_dim)
    return int(config.output_dim)


def feature_extractor_input_kind(config: FeatureExtractorConfig) -> Literal["tokens", "box"]:
    if isinstance(config, BoxCNNFeatureExtractorConfig):
        return "box"
    return "tokens"


def token_feature_extractor_max_tokens(config: FeatureExtractorConfig) -> int | None:
    if isinstance(config, TokenPerceiverFeatureExtractorConfig):
        return config.max_tokens
    if isinstance(config, TokenMLPFeatureExtractorConfig):
        return config.max_tokens
    raise ValueError(f"Feature extractor type does not support token max_tokens: {type(config)!r}")


def token_feature_extractor_ignore_inventory_power_tokens(config: FeatureExtractorConfig) -> bool:
    if isinstance(config, TokenPerceiverFeatureExtractorConfig):
        return config.ignore_inventory_power_tokens
    if isinstance(config, TokenMLPFeatureExtractorConfig):
        return config.ignore_inventory_power_tokens
    raise ValueError(f"Feature extractor type does not support token ignore_inventory_power_tokens: {type(config)!r}")


__all__ = [
    "BoxCNNFeatureExtractorConfig",
    "FeatureExtractorConfig",
    "TokenMLPFeatureExtractorConfig",
    "TokenPerceiverFeatureExtractorConfig",
    "feature_extractor_input_kind",
    "feature_extractor_output_dim",
    "token_feature_extractor_ignore_inventory_power_tokens",
    "token_feature_extractor_max_tokens",
]
