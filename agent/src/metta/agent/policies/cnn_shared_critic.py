from typing import List

from cortex.stacks import build_cortex_auto_config
from pydantic import ConfigDict, Field

from metta.agent.components.actor import ActionProbsConfig, ActorHeadConfig
from metta.agent.components.cnn_encoder import CNNEncoderConfig
from metta.agent.components.component_config import ComponentConfig
from metta.agent.components.cortex import CortexTDConfig
from metta.agent.components.misc import MLPConfig
from metta.agent.components.obs_shim import ObsShimBoxConfig
from metta.agent.components.shared_critic import SharedCriticConfig
from metta.agent.policy import Policy, PolicyArchitecture
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class CnnSharedCriticConfig(PolicyArchitecture):
    """CNN encoder policy with a MAPPO-style shared critic."""

    class_path: str = "metta.agent.policy_auto_builder.PolicyAutoBuilder"
    model_config = ConfigDict(populate_by_name=True)

    latent_dim: int = Field(default=128)
    actor_hidden: int = Field(default=256)
    critic_hidden: int = Field(default=512)

    pass_state_during_training: bool = False

    core_resnet_layers: int = 1
    core_resnet_pattern: str = "L"
    core_use_layer_norm: bool = False
    core_compile: bool = False

    agents_per_env_slice: int | None = None

    components: List[ComponentConfig] = []

    action_probs_config: ActionProbsConfig = ActionProbsConfig(in_key="logits")

    def make_policy(self, policy_env_info: PolicyEnvInterface) -> Policy:
        if self.components:
            return super().make_policy(policy_env_info)

        self.components = [
            ObsShimBoxConfig(
                in_key="env_obs",
                out_key="obs_normalizer",
            ),
            CNNEncoderConfig(
                in_key="obs_normalizer",
                out_key="encoded_obs",
            ),
            CortexTDConfig(
                in_key="encoded_obs",
                out_key="core",
                d_hidden=self.latent_dim,
                out_features=self.latent_dim,
                key_prefix="cnn_cortex_state",
                stack_cfg=build_cortex_auto_config(
                    d_hidden=self.latent_dim,
                    num_layers=self.core_resnet_layers,
                    pattern=self.core_resnet_pattern,
                    post_norm=self.core_use_layer_norm,
                    compile_blocks=self.core_compile,
                ),
                pass_state_during_training=self.pass_state_during_training,
            ),
            MLPConfig(
                in_key="core",
                out_key="actor_hidden",
                name="actor_mlp",
                in_features=self.latent_dim,
                hidden_features=[self.actor_hidden],
                out_features=self.actor_hidden,
            ),
            SharedCriticConfig(
                in_key="core",
                out_key="values",
                out_key_h="h_values",
                name="shared_critic",
                in_features=self.latent_dim,
                hidden_features=[self.critic_hidden],
                agents_per_env_slice=self.agents_per_env_slice,
            ),
            ActorHeadConfig(in_key="actor_hidden", out_key="logits", input_dim=self.actor_hidden),
        ]

        return super().make_policy(policy_env_info)
