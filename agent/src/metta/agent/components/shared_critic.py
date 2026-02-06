from __future__ import annotations

from typing import List

import torch
import torch.nn as nn
from pydantic import ConfigDict
from tensordict import TensorDict

import pufferlib.pytorch
from metta.agent.components.component_config import ComponentConfig


class SharedCriticConfig(ComponentConfig):
    """Shared critic head for MAPPO-style centralized value estimation.

    Assumptions for the contiguous env-id layout:
      A) Agent-id layout is env-major: agent_id = env_index * N + agent_index
      B) Every training_env_id slice returned by get_observations() satisfies:
         - len(slice) % N == 0
         - slice.start % N == 0 (starts on an env boundary)
      C) Sequential sampling and minibatch sizing are chosen so:
         minibatch_segments = minibatch_size // bptt_horizon is a multiple of N

    With these, a sequential minibatch of contiguous segments aligns to env-sized
    blocks, so we can reshape/group rows into [num_envs_in_mb, N, TT, ...].
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    in_key: str
    out_key: str  # leaving this in case another critic wants to use "values"
    out_key_h: str = "h_values"
    name: str = "shared_critic"
    hidden_features: List[int]
    in_features: int
    layer_init_std: float = 1.0
    allow_partial_envs: bool = True
    use_cross_attention: bool = False
    num_heads: int = 1
    attention_dropout: float = 0.0

    def make_component(self, env=None):
        agents_per_env = int(env.num_agents)
        return SharedCritic(config=self, agents_per_env=agents_per_env)


class SharedCritic(nn.Module):
    """Shared critic that concatenates per-env agent latents and broadcasts values."""

    def __init__(self, config: SharedCriticConfig, *, agents_per_env: int):
        super().__init__()
        self.config = config
        if agents_per_env <= 0:
            raise ValueError("agents_per_env must be a positive integer")
        self.agents_per_env = agents_per_env

        self._attn: nn.MultiheadAttention | None = None
        if self.config.use_cross_attention:
            if self.config.in_features % self.config.num_heads != 0:
                raise ValueError("in_features must be divisible by num_heads for cross-attention critic")
            self._attn = nn.MultiheadAttention(
                embed_dim=self.config.in_features,
                num_heads=self.config.num_heads,
                dropout=self.config.attention_dropout,
                batch_first=True,
            )
            critic_in = self.config.in_features
        else:
            critic_in = self.config.in_features * self.agents_per_env
        self._values = self._build_mlp(critic_in)
        self._h_values = self._build_mlp(critic_in)

    def _build_mlp(self, in_features: int) -> nn.Sequential:
        layers: List[nn.Module] = []
        dims = list(self.config.hidden_features) + [1]
        for i, dim in enumerate(dims):
            linear_layer = pufferlib.pytorch.layer_init(nn.Linear(in_features, dim), std=self.config.layer_init_std)
            layers.append(linear_layer)
            if i < len(dims) - 1:
                layers.append(nn.SiLU())
            in_features = dim
        return nn.Sequential(*layers)

    @staticmethod
    def _reshape_for_envs(
        x: torch.Tensor, agents_per_env: int, *, bptt: int, allow_partial_envs: bool
    ) -> tuple[torch.Tensor, int, int, int]:
        if bptt <= 0:
            raise ValueError("bptt must be positive for shared critic")
        if x.shape[0] % bptt != 0:
            raise ValueError("Input length must be divisible by bptt for shared critic")
        batch = x.shape[0] // bptt
        remainder = batch % agents_per_env
        if remainder != 0 and not allow_partial_envs:
            raise ValueError("Batch size must be divisible by agents_per_env for shared critic")

        pad_agents = (agents_per_env - remainder) % agents_per_env
        if pad_agents:
            pad_rows = pad_agents * bptt
            pad = torch.zeros((pad_rows, x.shape[-1]), device=x.device, dtype=x.dtype)
            x = torch.cat([x, pad], dim=0)
            batch = batch + pad_agents

        # Calculate number of environments by dividing batch size by agents per environment
        num_envs = batch // agents_per_env
        # Reshape from [B*TT, D] to [batch, bptt, D] - grouping timesteps into sequences
        x_seq = x.view(batch, bptt, -1)
        # Reshape to [num_envs, agents_per_env, bptt, D] - grouping agents by environment
        x_env = x_seq.view(num_envs, agents_per_env, bptt, -1)
        return x_env, num_envs, bptt, pad_agents

    def _flatten_env(self, x_env: torch.Tensor) -> torch.Tensor:
        # [E, N, TT, D] -> [E*TT, N*D]
        return x_env.permute(0, 2, 1, 3).reshape(x_env.shape[0] * x_env.shape[2], -1)

    @staticmethod
    def _build_padding_mask(
        num_envs: int, agents_per_env: int, bptt: int, pad_agents: int, device: torch.device
    ) -> torch.Tensor | None:
        if pad_agents <= 0:
            return None
        mask = torch.zeros((num_envs, agents_per_env), dtype=torch.bool, device=device)
        mask[-1, -pad_agents:] = True
        mask = mask[:, None, :].expand(-1, bptt, -1).reshape(num_envs * bptt, agents_per_env)
        return mask

    def forward(self, td: TensorDict) -> TensorDict:
        x = td[self.config.in_key]
        if x.dim() == 2:
            # Expect flat [B*TT, D] with metadata for sequential training.
            bptt = int(td["bptt"][0].item())
        else:
            raise ValueError(f"Expected 2D input for shared critic, got {tuple(x.shape)}")

        x_env, num_envs, bptt, pad_agents = self._reshape_for_envs(
            x,
            self.agents_per_env,
            bptt=bptt,
            allow_partial_envs=self.config.allow_partial_envs,
        )
        if self.config.use_cross_attention:
            # [E, N, TT, D] -> [E*TT, N, D] for per-env-time attention
            x_attn = x_env.permute(0, 2, 1, 3).reshape(num_envs * bptt, self.agents_per_env, -1)
            key_padding_mask = self._build_padding_mask(num_envs, self.agents_per_env, bptt, pad_agents, x_attn.device)
            # Cross-attention pooling: per-agent query attends to all agents in env.
            # Pyright needs explicit Optional narrowing here, even though use_cross_attention
            # drives _attn initialization in __init__, hence the assert below.
            assert self._attn is not None, "_attn should be initialized when use_cross_attention is True"
            attn_out, _ = self._attn(x_attn, x_attn, x_attn, key_padding_mask=key_padding_mask)
            attn_env = attn_out.view(num_envs, bptt, self.agents_per_env, -1).permute(0, 2, 1, 3).contiguous()
            attn_seq = attn_env.view(num_envs * self.agents_per_env, bptt, -1)
            x_flat = attn_seq.reshape(-1, attn_seq.shape[-1])
            values = self._values(x_flat)
            h_values = self._h_values(x_flat)
        else:
            x_flat = self._flatten_env(x_env)
            values = self._values(x_flat)
            h_values = self._h_values(x_flat)

            if bptt == 1:
                # [E, 1] -> [E, N, 1] -> [B, 1]
                values = values.view(num_envs, 1).expand(-1, self.agents_per_env).reshape(-1, 1)
                h_values = h_values.view(num_envs, 1).expand(-1, self.agents_per_env).reshape(-1, 1)
            else:
                # [E*TT, 1] -> [E, TT, 1] -> [E, N, TT, 1] -> [B, TT, 1] -> [B*TT, 1]
                values = values.view(num_envs, bptt, 1).unsqueeze(1)
                values = values.expand(-1, self.agents_per_env, -1, -1).reshape(-1, bptt, 1)
                values = values.reshape(-1, 1)
                h_values = h_values.view(num_envs, bptt, 1).unsqueeze(1)
                h_values = h_values.expand(-1, self.agents_per_env, -1, -1).reshape(-1, bptt, 1)
                h_values = h_values.reshape(-1, 1)

        if pad_agents:
            if bptt == 1:
                values = values[:-pad_agents]
                h_values = h_values[:-pad_agents]
            else:
                values = values[: -(pad_agents * bptt)]
                h_values = h_values[: -(pad_agents * bptt)]

        td[self.config.out_key] = values
        td[self.config.out_key_h] = h_values
        return td


__all__ = ["SharedCriticConfig", "SharedCritic"]
