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


class PufferLSTMConfig(PolicyArchitecture):
    """PufferLib 4.0 Default model with fast TT==1 path (LSTMCell), matching `forward_eval`."""

    class_path: str = "metta.agent.policies.puffer_lstm.PufferLSTMPolicy"
    hidden_size: int = 256
    num_layers: int = 1
    feature_extractor: FeatureExtractorConfig | None = None
    action_probs_config: ActionProbsConfig = ActionProbsConfig(in_key="logits")

    @model_validator(mode="after")
    def _set_default_feature_extractor(self) -> "PufferLSTMConfig":
        if self.feature_extractor is None:
            self.feature_extractor = TokenMLPFeatureExtractorConfig(
                output_dim=int(self.hidden_size),
                hidden_features=[],
                max_tokens=200,
                ignore_inventory_power_tokens=False,
            )
        return self


class PufferLSTMPolicy(Policy):
    def __init__(self, policy_env_info: PolicyEnvInterface, config: Optional[PufferLSTMConfig] = None):
        super().__init__(policy_env_info)
        self.config = config or PufferLSTMConfig()
        self.is_continuous = False
        self.action_space = policy_env_info.action_space

        hidden_size = int(self.config.hidden_size)
        num_layers = int(self.config.num_layers)
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

        self.lstm = nn.LSTM(hidden_size, hidden_size, num_layers=num_layers)
        self.cell = nn.ModuleList([nn.LSTMCell(hidden_size, hidden_size) for _ in range(num_layers)])

        # Mirror pufferlib.models.Default init: orthogonal weights, zero biases, and tie cell params.
        for i in range(num_layers):
            w_ih = getattr(self.lstm, f"weight_ih_l{i}")
            w_hh = getattr(self.lstm, f"weight_hh_l{i}")
            b_ih = getattr(self.lstm, f"bias_ih_l{i}")
            b_hh = getattr(self.lstm, f"bias_hh_l{i}")

            nn.init.orthogonal_(w_ih, 1.0)
            nn.init.orthogonal_(w_hh, 1.0)
            b_ih.data.zero_()
            b_hh.data.zero_()

            cell = self.cell[i]
            cell.weight_ih = w_ih
            cell.weight_hh = w_hh
            cell.bias_ih = b_ih
            cell.bias_hh = b_hh

        self.actor = pufferlib.pytorch.layer_init(nn.Linear(hidden_size, int(self.action_space.n)), std=0.01)
        self.value = pufferlib.pytorch.layer_init(nn.Linear(hidden_size, 1), std=1.0)
        self.gtd_aux = pufferlib.pytorch.layer_init(nn.Linear(hidden_size, 1), std=1.0)

        # Rollout-time recurrent state keyed by agent_slot_id.
        # Shape: (num_agents, num_layers, hidden_size)
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
        num_layers: int,
        hidden_size: int,
    ) -> torch.Tensor:
        if min_rows <= 0:
            min_rows = 1
        want = (min_rows, num_layers, hidden_size)
        if storage is None:
            return torch.zeros(want, device=device, dtype=dtype)
        if storage.device != device or storage.dtype != dtype:
            storage = storage.to(device=device, dtype=dtype)
        if storage.shape[0] >= min_rows and storage.shape[1:] == want[1:]:
            return storage
        grown = torch.zeros(want, device=device, dtype=dtype)
        rows = min(storage.shape[0], grown.shape[0])
        if storage.shape[1:] == grown.shape[1:]:
            grown[:rows].copy_(storage[:rows])
        return grown

    def forward(self, td: TensorDict, action: Optional[torch.Tensor] = None) -> TensorDict:
        obs = td["env_obs"]
        device = obs.device

        TT = int(td["bptt"][0].item())
        B = int(td["batch"][0].item())
        hidden_size = int(self.config.hidden_size)
        num_layers = int(self.config.num_layers)

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
                num_layers=num_layers,
                hidden_size=hidden_size,
            )
            self._rollout_c = self._ensure_capacity(
                self._rollout_c,
                max_agent,
                device=device,
                dtype=encoded.dtype,
                num_layers=num_layers,
                hidden_size=hidden_size,
            )

            h = self._rollout_h.index_select(0, agent_slot_ids)  # (B, L, H)
            c = self._rollout_c.index_select(0, agent_slot_ids)

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

            core = encoded.view(B, hidden_size)
            h_next = []
            c_next = []
            for i in range(num_layers):
                h_i, c_i = self.cell[i](core, (h[:, i], c[:, i]))
                core = h_i
                h_next.append(h_i)
                c_next.append(c_i)
            h_next_t = torch.stack(h_next, dim=1)
            c_next_t = torch.stack(c_next, dim=1)

            self._rollout_h.index_copy_(0, agent_slot_ids, h_next_t.detach())
            self._rollout_c.index_copy_(0, agent_slot_ids, c_next_t.detach())
        else:
            x_seq = encoded.view(B, TT, hidden_size).transpose(0, 1)  # (TT, B, H)
            y, _ = self.lstm(x_seq)
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
        self.obs_shim.initialize_to_environment(policy_env_info, device)
        self.action_probs.initialize_to_environment(policy_env_info, device)

    def reset_memory(self):
        self._rollout_h = None
        self._rollout_c = None

    def initial_agent_state(self) -> "PufferLSTMPolicy._AgentState":
        device = self.device
        hidden_size = int(self.config.hidden_size)
        num_layers = int(self.config.num_layers)
        h = torch.zeros((num_layers, 1, hidden_size), device=device)
        c = torch.zeros((num_layers, 1, hidden_size), device=device)
        return PufferLSTMPolicy._AgentState(h=h, c=c)

    def load_agent_state(self, state: Optional["PufferLSTMPolicy._AgentState"]) -> None:
        _ = state
        return

    def dump_agent_state(self) -> Optional["PufferLSTMPolicy._AgentState"]:
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
