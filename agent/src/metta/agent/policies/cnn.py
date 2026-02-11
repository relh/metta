from typing import List, Optional

import einops
import numpy as np
import torch
import torch.nn as nn
from cortex.stacks import build_cortex_auto_config
from tensordict import TensorDict
from torchrl.data import Composite, UnboundedDiscrete

import pufferlib.pytorch
from metta.agent.components.actor import ActionProbs, ActionProbsConfig
from metta.agent.components.cortex import CortexTD, CortexTDConfig
from metta.agent.policy import Policy, PolicyArchitecture
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.policy.token_encoder import coordinates

_CORTEX_HIDDEN = 128


class CnnConfig(PolicyArchitecture):
    """Policy with CNN encoder + Cortex sequence model."""

    class_path: str = "metta.agent.policies.cnn.CnnPolicy"
    action_probs_config: ActionProbsConfig = ActionProbsConfig(in_key="logits")
    cortex_core_config: CortexTDConfig = CortexTDConfig(
        in_key="encoded_obs",
        out_key="core",
        d_hidden=_CORTEX_HIDDEN,
        out_features=_CORTEX_HIDDEN,
        key_prefix="cnn_cortex_state",
        pass_state_during_training=True,
        stack_cfg=build_cortex_auto_config(
            d_hidden=_CORTEX_HIDDEN,
            num_layers=2,
            pattern="Ag,A,S",
            post_norm=False,
        ),
    )
    critic_hidden_dim: int = 1024
    actor_hidden_dim: int = 512


class _OptionalLoadLinear(nn.Linear):
    def _load_from_state_dict(
        self,
        state_dict,
        prefix,
        local_metadata,
        strict,
        missing_keys,
        unexpected_keys,
        error_msgs,
    ):
        weight_key = prefix + "weight"
        if weight_key not in state_dict:
            return
        super()._load_from_state_dict(
            state_dict,
            prefix,
            local_metadata,
            strict,
            missing_keys,
            unexpected_keys,
            error_msgs,
        )


class CnnPolicy(Policy):
    """CNN encoder + Cortex sequence model.

    Architecture: CNN (3x3 stride 2) + self-encoder -> projection -> Cortex(128) -> actor/critic heads.
    """

    _feature_scale: torch.Tensor

    def __init__(self, policy_env_info: PolicyEnvInterface, config: Optional[CnnConfig] = None):
        super().__init__(policy_env_info)

        self.config = config or CnnConfig()
        self.is_continuous = False
        self.action_space = policy_env_info.action_space
        self.out_width = policy_env_info.obs_width
        self.out_height = policy_env_info.obs_height

        self.num_features = max((int(f.id) for f in policy_env_info.obs_features), default=0) + 1

        # Feature normalization
        feature_norms = {f.id: f.normalization for f in policy_env_info.obs_features}
        max_id = max((int(fid) for fid in feature_norms.keys()), default=-1)
        feature_scale = torch.ones(max(256, max_id + 1), dtype=torch.float32)
        for fid, norm in feature_norms.items():
            feature_scale[fid] = max(float(norm), 1.0)
        self.register_buffer("_feature_scale", feature_scale)

        # CNN encoder: 3x3 kernels, stride 2, padding 1
        self.cnn = nn.Sequential(
            nn.Conv2d(self.num_features, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.Flatten(),
        )

        with torch.no_grad():
            dummy = torch.zeros(1, self.num_features, self.out_height, self.out_width)
            cnn_out_size = self.cnn(dummy).shape[1]

        self.cnn_fc = nn.Linear(cnn_out_size, 256)
        self.self_encoder = nn.Linear(self.num_features, 256)

        # Project CNN output (512) down to cortex hidden size
        cortex_hidden = self.config.cortex_core_config.d_hidden
        self.cnn_projection = nn.Linear(512, cortex_hidden)

        # Cortex sequence model
        self.core = CortexTD(config=self.config.cortex_core_config)
        core_width = int(self.config.cortex_core_config.out_features or cortex_hidden)

        # Actor head
        self.actor_1 = pufferlib.pytorch.layer_init(nn.Linear(core_width, self.config.actor_hidden_dim), std=1.0)
        self.actor_logits = pufferlib.pytorch.layer_init(
            nn.Linear(self.config.actor_hidden_dim, len(policy_env_info.action_names)), std=0.01
        )

        # Critic head
        self.critic_1 = pufferlib.pytorch.layer_init(
            nn.Linear(core_width, self.config.critic_hidden_dim), std=np.sqrt(2)
        )
        self.critic_activation = nn.Tanh()
        self.value_head = pufferlib.pytorch.layer_init(nn.Linear(self.config.critic_hidden_dim, 1), std=1.0)
        self.gtd_aux = pufferlib.pytorch.layer_init(_OptionalLoadLinear(self.config.critic_hidden_dim, 1), std=1.0)

        # Action probabilities component
        self.action_probs = ActionProbs(config=self.config.action_probs_config)

    def _tokens_to_grid(self, observations: torch.Tensor) -> torch.Tensor:
        """Convert token observations [B, T, 3] to grid [B, C, H, W]."""
        batch_size = observations.shape[0]
        device = observations.device

        x_coords, y_coords = coordinates(observations, torch.long)
        feature_ids = observations[..., 1].to(torch.long)
        values = observations[..., 2].to(torch.float32)

        valid_mask = observations[..., 0] != 0xFF
        x_coords = torch.clamp(x_coords, 0, self.out_width - 1)
        y_coords = torch.clamp(y_coords, 0, self.out_height - 1)
        feature_ids_clamped = torch.clamp(feature_ids, 0, self.num_features - 1)

        scale = self._feature_scale[torch.clamp(feature_ids, 0, self._feature_scale.shape[0] - 1)]
        values = (values / (scale + 1e-6)) * valid_mask.float()

        grid = torch.zeros(batch_size, self.num_features, self.out_height, self.out_width, device=device)
        batch_idx = torch.arange(batch_size, device=device).unsqueeze(1).expand_as(x_coords)
        linear_idx = (
            batch_idx * (self.num_features * self.out_height * self.out_width)
            + feature_ids_clamped * (self.out_height * self.out_width)
            + y_coords * self.out_width
            + x_coords
        )
        grid.view(-1).scatter_add_(0, linear_idx.view(-1), values.view(-1))
        return grid

    def encode_observations(self, observations: torch.Tensor) -> torch.Tensor:
        """Encode observations through CNN + self-encoder.

        Handles both single-step [B, M, 3] and BPTT [B, T, M, 3] inputs.
        """
        if observations.dim() != 3:
            observations = einops.rearrange(observations, "b t m c -> (b t) m c")

        grid = self._tokens_to_grid(observations)

        # CNN path
        cnn_out = torch.relu(self.cnn_fc(self.cnn(grid)))

        # Self-encoder: center cell features
        center = grid[:, :, self.out_height // 2, self.out_width // 2]
        self_out = torch.relu(self.self_encoder(center))

        # Concat: [B*T, 256] + [B*T, 256] = [B*T, 512]
        combined = torch.cat([cnn_out, self_out], dim=-1)

        # Project to cortex hidden size
        return self.cnn_projection(combined)

    @torch._dynamo.disable
    def forward(self, td: TensorDict, state=None, action: Optional[torch.Tensor] = None):
        observations = td["env_obs"]

        encoded_obs = self.encode_observations(observations)
        td["encoded_obs"] = encoded_obs

        self.core(td)
        core_features = td["core"]

        # Actor
        actor_hidden = torch.relu(self.actor_1(core_features))
        logits = self.actor_logits(actor_hidden)

        # Critic
        critic_hidden = self.critic_activation(self.critic_1(core_features))
        value = self.value_head(critic_hidden)
        h_value = self.gtd_aux(critic_hidden)

        td["logits"] = logits
        td["values"] = value.flatten()
        td["h_values"] = h_value.flatten()
        self.action_probs(td, action)

        return td

    def initialize_to_environment(self, policy_env_info: PolicyEnvInterface, device: torch.device) -> List[str | None]:
        self.to(device)
        self.core.initialize_to_environment(policy_env_info, device)
        self.action_probs.initialize_to_environment(policy_env_info, device)
        return []

    def reset_memory(self):
        self.core.reset_memory()

    def get_agent_experience_spec(self) -> Composite:
        spec = Composite(
            env_obs=UnboundedDiscrete(shape=torch.Size([200, 3]), dtype=torch.uint8),
            dones=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.float32),
            truncateds=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.float32),
        )
        for key, shape in self.core.experience_keys().items():
            if key not in spec.keys():
                long_keys = ("training_env_ids", "row_id", "t_in_row", "agent_slot_ids")
                dtype = torch.long if key in long_keys else torch.float32
                spec.set(key, UnboundedDiscrete(shape=torch.Size(shape), dtype=dtype))
        return spec

    @property
    def device(self) -> torch.device:
        return next(self.parameters()).device

    @property
    def action_names(self) -> list[str]:
        return list(self.policy_env_info.action_names)

    @property
    def observation_space(self):
        return self.policy_env_info.observation_space
