from __future__ import annotations

import torch
import torch.nn as nn
from cortex.rl.feature_extractors import (
    FeatureExtractorConfig,
    build_feature_extractor,
    feature_extractor_input_kind,
)
from tensordict import TensorDict

from metta.agent.components.component_config import ComponentConfig
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class FeatureExtractorComponentConfig(ComponentConfig):
    in_key: str
    out_key: str
    feature_extractor: FeatureExtractorConfig
    name: str = "feature_extractor"

    def make_component(self, policy_env_interface: PolicyEnvInterface) -> nn.Module:
        return FeatureExtractorComponent(config=self, policy_env_interface=policy_env_interface)


class FeatureExtractorComponent(nn.Module):
    def __init__(self, config: FeatureExtractorComponentConfig, policy_env_interface: PolicyEnvInterface) -> None:
        super().__init__()
        self.config = config

        input_kind = feature_extractor_input_kind(self.config.feature_extractor)
        self._expects_tokens = input_kind == "tokens"

        if self._expects_tokens:
            self.extractor = build_feature_extractor(self.config.feature_extractor)
            return

        in_channels = _resolve_box_channels(policy_env_interface)
        input_hw = (int(policy_env_interface.obs_height), int(policy_env_interface.obs_width))
        self.extractor = build_feature_extractor(
            self.config.feature_extractor,
            in_channels=in_channels,
            input_hw=input_hw,
        )

    def forward(self, td: TensorDict) -> TensorDict:
        x = td[self.config.in_key]
        if self._expects_tokens:
            obs_mask = td.get("obs_mask")
            if obs_mask is not None and obs_mask.dtype != torch.bool:
                obs_mask = obs_mask.to(dtype=torch.bool)
            y = self.extractor(x, obs_mask=obs_mask)
        else:
            y = self.extractor(x)
        td[self.config.out_key] = y
        return td


def _resolve_box_channels(policy_env_interface: PolicyEnvInterface) -> int:
    if policy_env_interface.obs_features:
        return max(feat.id for feat in policy_env_interface.obs_features) + 1

    obs_shape = getattr(policy_env_interface.observation_space, "shape", None)
    if not obs_shape:
        raise ValueError("Cannot infer box observation channels from policy environment interface")
    return int(obs_shape[0])


__all__ = ["FeatureExtractorComponent", "FeatureExtractorComponentConfig"]
