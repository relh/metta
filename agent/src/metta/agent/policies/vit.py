from typing import List, Optional

from cortex.config import RoutedAdapterConfig
from cortex.stacks import build_cortex_auto_config
from pydantic import ConfigDict, Field

from metta.agent.components.actor import ActionProbsConfig, ActorHeadConfig
from metta.agent.components.component_config import ComponentConfig
from metta.agent.components.cortex import CortexTDConfig
from metta.agent.components.misc import MLPConfig, ReshapeActionsFeaturesConfig, SplitFirstFeaturesConfig
from metta.agent.components.obs_enc import ObsPerceiverLatentConfig
from metta.agent.components.obs_shim import ObsShimTokensConfig
from metta.agent.components.obs_tokenizers import ObsAttrEmbedFourierConfig
from metta.agent.policy import Policy, PolicyArchitecture
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class ViTDefaultConfig(PolicyArchitecture):
    """Speed-optimized ViT variant with lighter token embeddings and attention stack.

    The trunk uses Axon blocks (post-up experts with residual connections) for efficient
    feature processing. Configure trunk depth, layer normalization, and hidden dimension
    scaling independently.
    """

    class_path: str = "metta.agent.policy_auto_builder.PolicyAutoBuilder"
    model_config = ConfigDict(populate_by_name=True)

    _token_embed_dim = 8
    _fourier_freqs = 3
    # Defaults aligned with legacy CvC baseline (keep max_tokens from newer runs)
    latent_dim: int = Field(default=128)
    actor_hidden: int = Field(default=256)
    core_num_heads: int = Field(default=4)
    max_tokens: int = Field(default=128)
    core_num_latents: int = Field(default=12)
    obs_shim_ignore_inventory_power_tokens: bool = True

    # Whether training passes cached pre-state to the Cortex core
    pass_state_during_training: bool = False
    critic_hidden: int = Field(default=512)
    horde_num_cumulants: int = Field(default=0, ge=0)
    horde_hidden: int = Field(default=256, ge=1)
    horde_action_conditioned: bool = False

    # Trunk configuration
    # Number of Axon layers in the trunk
    core_resnet_layers: int = 2
    # Pattern for trunk layers (e.g., "A" for Axon blocks, "L" for linear)
    core_resnet_pattern: str = "Ag,A,S"
    # Enable layer normalization after each trunk layer
    core_use_layer_norm: bool = False
    # Whether to torch.compile the trunk (Cortex stack)
    core_compile: bool = False

    core_routed_adapter: Optional[RoutedAdapterConfig] = None

    components: List[ComponentConfig] = []

    action_probs_config: ActionProbsConfig = ActionProbsConfig(in_key="logits")

    def make_policy(self, policy_env_info: PolicyEnvInterface) -> Policy:
        # If the architecture spec already bundled a component list (common for saved
        # checkpoint bundles), reuse it instead of regenerating with current defaults.
        # This keeps restored policies aligned with the shapes they were trained with.
        if self.components:
            return super().make_policy(policy_env_info)

        self.components = [
            ObsShimTokensConfig(
                in_key="env_obs",
                out_key="obs_shim_tokens",
                max_tokens=self.max_tokens,
                ignore_inventory_power_tokens=self.obs_shim_ignore_inventory_power_tokens,
            ),
            ObsAttrEmbedFourierConfig(
                in_key="obs_shim_tokens",
                out_key="obs_attr_embed",
                attr_embed_dim=self._token_embed_dim,
                num_freqs=self._fourier_freqs,
            ),
            ObsPerceiverLatentConfig(
                in_key="obs_attr_embed",
                out_key="obs_latent_attn",
                feat_dim=self._token_embed_dim + (4 * self._fourier_freqs) + 1,
                latent_dim=self.latent_dim,
                num_latents=self.core_num_latents,
                num_heads=self.core_num_heads,
                num_layers=1,
            ),
            CortexTDConfig(
                in_key="obs_latent_attn",
                out_key="core",
                d_hidden=self.latent_dim,
                out_features=self.latent_dim,
                key_prefix="vit_cortex_state",
                stack_cfg=build_cortex_auto_config(
                    d_hidden=self.latent_dim,
                    num_layers=self.core_resnet_layers,
                    pattern=self.core_resnet_pattern,
                    post_norm=self.core_use_layer_norm,
                    compile_blocks=self.core_compile,
                    routed_adapter=self.core_routed_adapter,
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
        ]

        horde_enabled = self.horde_num_cumulants > 0
        use_state_horde_bank = horde_enabled and not self.horde_action_conditioned
        critic_out_features = 1 + self.horde_num_cumulants if use_state_horde_bank else 1

        psi_key = "gtd_psi_all" if use_state_horde_bank else "values"
        self.components.append(
            MLPConfig(
                in_key="core",
                out_key=psi_key,
                name="critic",
                in_features=self.latent_dim,
                out_features=critic_out_features,
                hidden_features=[self.critic_hidden],
            )
        )
        if use_state_horde_bank:
            self.components.append(
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
        self.components.append(
            MLPConfig(
                in_key="core",
                out_key=h_key,
                name="gtd_aux",
                in_features=self.latent_dim,
                out_features=critic_out_features,
                hidden_features=[self.critic_hidden],
            )
        )
        if use_state_horde_bank:
            self.components.append(
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
                self.components.append(
                    MLPConfig(
                        in_key="core",
                        out_key=flat_key,
                        name=f"horde_{kind}_head",
                        in_features=self.latent_dim,
                        out_features=num_actions * self.horde_num_cumulants,
                        hidden_features=[self.horde_hidden],
                    )
                )
                self.components.append(
                    ReshapeActionsFeaturesConfig(
                        in_key=flat_key,
                        out_key=all_actions_key,
                        num_actions=num_actions,
                        num_features=self.horde_num_cumulants,
                        name=f"reshape_horde_{kind}",
                    )
                )

        self.components.append(ActorHeadConfig(in_key="actor_hidden", out_key="logits", input_dim=self.actor_hidden))
        return super().make_policy(policy_env_info)
