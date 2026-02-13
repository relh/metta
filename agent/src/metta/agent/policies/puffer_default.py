from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
from cortex.rl.feature_extractors import (
    FeatureExtractorConfig,
    TokenMLPFeatureExtractorConfig,
    feature_extractor_input_kind,
    feature_extractor_output_dim,
    token_feature_extractor_ignore_inventory_power_tokens,
    token_feature_extractor_max_tokens,
)
from pydantic import model_validator
from tensordict import TensorDict
from torchrl.data import Composite, UnboundedDiscrete

import pufferlib.pytorch
from metta.agent.components.actor import ActionProbs, ActionProbsConfig
from metta.agent.components.feature_extractor import FeatureExtractorComponent, FeatureExtractorComponentConfig
from metta.agent.components.obs_shim import ObsShimBox, ObsShimBoxConfig, ObsShimTokens, ObsShimTokensConfig
from metta.agent.policy import Policy, PolicyArchitecture
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class PufferDefaultConfig(PolicyArchitecture):
    """PufferLib-style LSTM policy with Cortex feature-extractor front-end."""

    class_path: str = "metta.agent.policies.puffer_default.PufferDefaultPolicy"
    hidden_size: int = 256
    feature_extractor: FeatureExtractorConfig | None = None
    action_probs_config: ActionProbsConfig = ActionProbsConfig(in_key="logits")

    @model_validator(mode="after")
    def _set_default_feature_extractor(self) -> "PufferDefaultConfig":
        if self.feature_extractor is None:
            self.feature_extractor = TokenMLPFeatureExtractorConfig(
                output_dim=int(self.hidden_size),
                hidden_features=[],
                max_tokens=200,
                ignore_inventory_power_tokens=False,
            )
        return self


class PufferDefaultPolicy(Policy):
    """Metta-trainer-compatible implementation of PufferLib's Default+LSTM policy."""

    def __init__(self, policy_env_info: PolicyEnvInterface, config: Optional[PufferDefaultConfig] = None):
        super().__init__(policy_env_info)
        self.config = config or PufferDefaultConfig()
        self.is_continuous = False
        self.action_space = policy_env_info.action_space

        hidden_size = int(self.config.hidden_size)
        feature_extractor_cfg = self.config.feature_extractor
        if feature_extractor_cfg is None:
            raise ValueError("feature_extractor must be configured")

        extractor_input_kind = feature_extractor_input_kind(feature_extractor_cfg)
        if extractor_input_kind == "tokens":
            self.obs_shim: ObsShimTokens | ObsShimBox = ObsShimTokens(
                policy_env_info,
                config=ObsShimTokensConfig(
                    in_key="env_obs",
                    out_key="obs_features_input",
                    max_tokens=token_feature_extractor_max_tokens(feature_extractor_cfg),
                    ignore_inventory_power_tokens=token_feature_extractor_ignore_inventory_power_tokens(
                        feature_extractor_cfg
                    ),
                ),
            )
        elif extractor_input_kind == "box":
            self.obs_shim = ObsShimBox(
                policy_env_info,
                config=ObsShimBoxConfig(in_key="env_obs", out_key="obs_features_input"),
            )
        else:
            raise ValueError(f"Unsupported feature extractor input kind: {extractor_input_kind}")

        self.feature_extractor = FeatureExtractorComponent(
            config=FeatureExtractorComponentConfig(
                in_key="obs_features_input",
                out_key="obs_features",
                feature_extractor=feature_extractor_cfg,
            ),
            policy_env_interface=policy_env_info,
        )
        extractor_out_dim = int(feature_extractor_output_dim(feature_extractor_cfg))
        if extractor_out_dim == hidden_size:
            self.encoder_projection: nn.Module = nn.Identity()
        else:
            self.encoder_projection = pufferlib.pytorch.layer_init(nn.Linear(extractor_out_dim, hidden_size))

        self.lstm = nn.LSTM(hidden_size, hidden_size, num_layers=1)

        # Mirror pufferlib.models.Default init: orthogonal weights, zero biases
        for name, param in self.lstm.named_parameters():
            if "bias" in name:
                nn.init.constant_(param, 0.0)
            elif "weight" in name:
                nn.init.orthogonal_(param, 1.0)

        self.actor = pufferlib.pytorch.layer_init(nn.Linear(hidden_size, int(self.action_space.n)), std=0.01)
        self.value = pufferlib.pytorch.layer_init(nn.Linear(hidden_size, 1), std=1.0)
        self.gtd_aux = pufferlib.pytorch.layer_init(nn.Linear(hidden_size, 1), std=1.0)

        # Rollout-time recurrent state keyed by agent_slot_id
        self._rollout_h: torch.Tensor | None = None
        self._rollout_c: torch.Tensor | None = None

        self.action_probs = ActionProbs(config=self.config.action_probs_config)

    @dataclass
    class _AgentState:
        h: torch.Tensor
        c: torch.Tensor

    def _ensure_capacity(
        self,
        storage: torch.Tensor | None,
        min_rows: int,
        *,
        device: torch.device,
        dtype: torch.dtype,
        hidden_size: int,
    ) -> torch.Tensor:
        if min_rows <= 0:
            min_rows = 1
        if storage is None:
            return torch.zeros((min_rows, hidden_size), device=device, dtype=dtype)
        if storage.device != device or storage.dtype != dtype:
            storage = storage.to(device=device, dtype=dtype)
        if storage.shape[0] >= min_rows:
            return storage
        grown = torch.zeros((min_rows, hidden_size), device=device, dtype=dtype)
        grown[: storage.shape[0]].copy_(storage)
        return grown

    @torch._dynamo.disable  # Avoid Dynamo overhead in the rollout hot path.
    def forward(self, td: TensorDict, state=None, action: Optional[torch.Tensor] = None):
        _ = state
        obs = td["env_obs"]
        device = obs.device

        TT = int(td["bptt"][0].item())
        B = int(td["batch"][0].item())
        hidden_size = int(self.config.hidden_size)

        self.obs_shim(td)
        self.feature_extractor(td)
        encoded = self.encoder_projection(td["obs_features"])

        if TT == 1:
            agent_slot_ids_2d = td["agent_slot_ids"].to(device=device, dtype=torch.long)
            if agent_slot_ids_2d.dim() != 2 or agent_slot_ids_2d.shape[1] != 1:
                raise ValueError(f"agent_slot_ids must have shape [B*TT,1], got {tuple(agent_slot_ids_2d.shape)}")
            agent_slot_ids = agent_slot_ids_2d.reshape(-1)
            if agent_slot_ids.numel() != B:
                raise ValueError(f"agent_slot_ids length {agent_slot_ids.numel()} must equal B ({B}) for TT==1")

            max_agent = int(agent_slot_ids.max().item()) + 1 if agent_slot_ids.numel() else 1
            self._rollout_h = self._ensure_capacity(
                self._rollout_h,
                max_agent,
                device=device,
                dtype=encoded.dtype,
                hidden_size=hidden_size,
            )
            self._rollout_c = self._ensure_capacity(
                self._rollout_c,
                max_agent,
                device=device,
                dtype=encoded.dtype,
                hidden_size=hidden_size,
            )

            h = self._rollout_h.index_select(0, agent_slot_ids)
            c = self._rollout_c.index_select(0, agent_slot_ids)

            # Reset state when env reports terminal/truncation (obs is post-reset in vecenv semantics).
            dones = td.get("dones")
            truncateds = td.get("truncateds")
            if dones is not None or truncateds is not None:
                if dones is None:
                    dones = torch.zeros((B,), device=device, dtype=torch.float32)
                if truncateds is None:
                    truncateds = torch.zeros((B,), device=device, dtype=torch.float32)
                reset_mask = (dones.view(-1) > 0.0) | (truncateds.view(-1) > 0.0)
                if bool(reset_mask.any()):
                    h = h.clone()
                    c = c.clone()
                    h[reset_mask] = 0
                    c[reset_mask] = 0

            # LSTM expects (seq, batch, hidden)
            x = encoded.view(B, hidden_size).unsqueeze(0)
            y, (h_next, c_next) = self.lstm(x, (h.unsqueeze(0), c.unsqueeze(0)))
            core = y.squeeze(0)

            # Update rollout state store
            self._rollout_h.index_copy_(0, agent_slot_ids, h_next.squeeze(0).detach())
            self._rollout_c.index_copy_(0, agent_slot_ids, c_next.squeeze(0).detach())
        else:
            x = encoded.view(B, TT, hidden_size).transpose(0, 1)  # (TT, B, H)
            # PufferLib's training forward uses the LSTM default (zero) initial state.
            y, _ = self.lstm(x)
            core = y.transpose(0, 1).reshape(B * TT, hidden_size)

        logits = self.actor(core)
        values = self.value(core).squeeze(-1)
        h_values = self.gtd_aux(core).squeeze(-1)

        td["logits"] = logits
        td["values"] = values
        td["h_values"] = h_values
        self.action_probs(td, action)

        return td

    def initialize_to_environment(self, policy_env_info: PolicyEnvInterface, device: torch.device):
        self.to(device)
        if hasattr(self.obs_shim, "initialize_to_environment"):
            self.obs_shim.initialize_to_environment(policy_env_info, device)
        self.action_probs.initialize_to_environment(policy_env_info, device)

    def reset_memory(self):
        # Ensure stale rollout recurrent state never leaks across episodes/sim resets.
        self._rollout_h = None
        self._rollout_c = None

    def initial_agent_state(self) -> "PufferDefaultPolicy._AgentState":
        device = self.device
        h = torch.zeros((1, 1, int(self.config.hidden_size)), device=device)
        c = torch.zeros((1, 1, int(self.config.hidden_size)), device=device)
        return PufferDefaultPolicy._AgentState(h=h, c=c)

    def load_agent_state(self, state: Optional["PufferDefaultPolicy._AgentState"]) -> None:
        # The generic per-agent stepping path is low-traffic; we rely on agent_slot_ids-based storage in forward().
        _ = state
        return

    def dump_agent_state(self) -> Optional["PufferDefaultPolicy._AgentState"]:
        return None

    def get_agent_experience_spec(self) -> Composite:
        return Composite(
            env_obs=UnboundedDiscrete(shape=torch.Size([200, 3]), dtype=torch.uint8),
            dones=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.float32),
            truncateds=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.float32),
            agent_slot_ids=UnboundedDiscrete(shape=torch.Size([1]), dtype=torch.int64),
        )

    @property
    def device(self) -> torch.device:
        return next(self.parameters()).device
