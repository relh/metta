from __future__ import annotations

from typing import List, Optional

from cortex.config import RoutedAdapterConfig
from cortex.rl.feature_extractors import (
    FeatureExtractorConfig,
    TokenPerceiverFeatureExtractorConfig,
    feature_extractor_input_kind,
    feature_extractor_output_dim,
    token_feature_extractor_ignore_inventory_power_tokens,
    token_feature_extractor_max_tokens,
)
from cortex.stacks import build_cortex_auto_config
from pydantic import ConfigDict, Field

from metta.agent.components.actor import ActionProbsConfig, ActorHeadConfig
from metta.agent.components.component_config import ComponentConfig
from metta.agent.components.cortex import CortexTDConfig
from metta.agent.components.feature_extractor import FeatureExtractorComponentConfig
from metta.agent.components.misc import MLPConfig, ReshapeActionsFeaturesConfig, SplitFirstFeaturesConfig
from metta.agent.components.obs_shim import ObsShimBoxConfig, ObsShimTokensConfig
from metta.agent.policy import Policy, PolicyArchitecture
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class CorePolicyConfig(PolicyArchitecture):
    """Default Cortex policy with pluggable feature extractors."""

    class_path: str = "metta.agent.policy_auto_builder.PolicyAutoBuilder"
    model_config = ConfigDict(populate_by_name=True)

    # Generic extractor interface.
    feature_extractor: FeatureExtractorConfig = Field(default_factory=TokenPerceiverFeatureExtractorConfig)
    actor_hidden: int = Field(default=256)

    pass_state_during_training: bool = False
    critic_hidden: int = Field(default=512)
    horde_num_cumulants: int = Field(default=0, ge=0)
    horde_hidden: int = Field(default=256, ge=1)
    horde_action_conditioned: bool = False

    # Cortex trunk configuration
    cortex_num_layers: int = 2
    cortex_pattern: str = "Ag,A,S"
    cortex_use_layer_norm: bool = False
    cortex_compile: bool = False
    cortex_routed_adapter: Optional[RoutedAdapterConfig] = None

    components: List[ComponentConfig] = []

    action_probs_config: ActionProbsConfig = ActionProbsConfig(in_key="logits")

    def make_policy(self, policy_env_info: PolicyEnvInterface) -> Policy:
        if self.components:
            return super().make_policy(policy_env_info)

        extractor_cfg = self.feature_extractor
        extractor_input_kind = feature_extractor_input_kind(extractor_cfg)
        extractor_out_dim = feature_extractor_output_dim(extractor_cfg)

        components: list[ComponentConfig] = []
        if extractor_input_kind == "tokens":
            components.append(
                ObsShimTokensConfig(
                    in_key="env_obs",
                    out_key="obs_features_input",
                    max_tokens=token_feature_extractor_max_tokens(extractor_cfg),
                    ignore_inventory_power_tokens=token_feature_extractor_ignore_inventory_power_tokens(extractor_cfg),
                )
            )
        elif extractor_input_kind == "box":
            components.append(ObsShimBoxConfig(in_key="env_obs", out_key="obs_features_input"))
        else:
            raise ValueError(f"Unsupported feature extractor input kind: {extractor_input_kind}")

        components.append(
            FeatureExtractorComponentConfig(
                in_key="obs_features_input",
                out_key="obs_features",
                feature_extractor=extractor_cfg,
            )
        )

        components.append(
            CortexTDConfig(
                in_key="obs_features",
                out_key="core",
                d_hidden=extractor_out_dim,
                out_features=extractor_out_dim,
                key_prefix="cortex_policy_state",
                stack_cfg=build_cortex_auto_config(
                    d_hidden=extractor_out_dim,
                    num_layers=self.cortex_num_layers,
                    pattern=self.cortex_pattern,
                    post_norm=self.cortex_use_layer_norm,
                    compile_blocks=self.cortex_compile,
                    routed_adapter=self.cortex_routed_adapter,
                ),
                pass_state_during_training=self.pass_state_during_training,
            )
        )

        components.append(
            MLPConfig(
                in_key="core",
                out_key="actor_hidden",
                name="actor_mlp",
                in_features=extractor_out_dim,
                hidden_features=[self.actor_hidden],
                out_features=self.actor_hidden,
            )
        )

        horde_enabled = self.horde_num_cumulants > 0
        use_state_horde_bank = horde_enabled and not self.horde_action_conditioned
        critic_out_features = 1 + self.horde_num_cumulants if use_state_horde_bank else 1

        psi_key = "gtd_psi_all" if use_state_horde_bank else "values"
        components.append(
            MLPConfig(
                in_key="core",
                out_key=psi_key,
                name="critic",
                in_features=extractor_out_dim,
                out_features=critic_out_features,
                hidden_features=[self.critic_hidden],
            )
        )
        if use_state_horde_bank:
            components.append(
                SplitFirstFeaturesConfig(
                    in_key=psi_key,
                    out_key_first="values",
                    out_key_rest="horde_psi",
                    first_features=1,
                    drop_in_key=True,
                    name="split_values_horde",
                )
            )

        h_key = "gtd_h_all" if use_state_horde_bank else "h_values"
        components.append(
            MLPConfig(
                in_key="core",
                out_key=h_key,
                name="gtd_aux",
                in_features=extractor_out_dim,
                out_features=critic_out_features,
                hidden_features=[self.critic_hidden],
            )
        )
        if use_state_horde_bank:
            components.append(
                SplitFirstFeaturesConfig(
                    in_key=h_key,
                    out_key_first="h_values",
                    out_key_rest="horde_h",
                    first_features=1,
                    drop_in_key=True,
                    name="split_h_values_horde",
                )
            )

        if horde_enabled and self.horde_action_conditioned:
            num_actions = int(policy_env_info.action_space.n)
            for kind in ("psi", "h"):
                flat_key = f"horde_{kind}_flat"
                all_actions_key = f"horde_{kind}_all_actions"
                components.append(
                    MLPConfig(
                        in_key="core",
                        out_key=flat_key,
                        name=f"horde_{kind}_head",
                        in_features=extractor_out_dim,
                        out_features=num_actions * self.horde_num_cumulants,
                        hidden_features=[self.horde_hidden],
                    )
                )
                components.append(
                    ReshapeActionsFeaturesConfig(
                        in_key=flat_key,
                        out_key=all_actions_key,
                        num_actions=num_actions,
                        num_features=self.horde_num_cumulants,
                        name=f"reshape_horde_{kind}",
                    )
                )

        components.append(ActorHeadConfig(in_key="actor_hidden", out_key="logits", input_dim=self.actor_hidden))
        self.components = components
        return super().make_policy(policy_env_info)


__all__ = ["CorePolicyConfig"]
