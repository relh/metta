import math
from typing import Literal, Optional

import torch
import torch.nn as nn
from gymnasium.spaces import Discrete
from pydantic import ConfigDict
from tensordict import TensorDict
from tensordict.nn import TensorDictModule as TDM

import pufferlib.pytorch
from metta.agent.components.component_config import ComponentConfig
from metta.agent.util.distribution_utils import evaluate_actions, sample_actions
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class ActorQueryConfig(ComponentConfig):
    in_key: str
    out_key: str
    name: str = "actor_query"
    hidden_size: int = 512
    embed_dim: int = 16

    def make_component(self, env=None):
        return ActorQuery(config=self)


class ActorQuery(nn.Module):
    def __init__(self, config: ActorQueryConfig):
        super().__init__()
        self.config = config
        self.hidden_size = self.config.hidden_size  # input_1 dim
        self.embed_dim = self.config.embed_dim  # input_2 dim (_action_embeds_)
        self.in_key = self.config.in_key
        self.out_key = self.config.out_key

        self.W = nn.Parameter(torch.empty(self.hidden_size, self.embed_dim, dtype=torch.float32))
        self._tanh = nn.Tanh()
        self._init_weights()

    def _init_weights(self):
        """Kaiming (He) initialization"""
        bound = 1 / math.sqrt(self.hidden_size)
        nn.init.uniform_(self.W, -bound, bound)

    def forward(self, td: TensorDict):
        hidden = td[self.in_key]  # Shape: [B*TT, hidden]

        query = torch.einsum("b h, h e -> b e", hidden, self.W)  # Shape: [B*TT, embed_dim]
        query = self._tanh(query)

        td[self.out_key] = query
        return td


class ActorKeyConfig(ComponentConfig):
    query_key: str
    embedding_key: str
    out_key: str
    name: str = "actor_key"
    hidden_size: int = 128
    embed_dim: int = 16

    def make_component(self, env=None):
        return ActorKey(config=self)


class ActorKey(nn.Module):
    """
    Computes action scores based on a query and action embeddings (keys).
    """

    def __init__(self, config: ActorKeyConfig):
        super().__init__()
        self.config = config
        self.hidden_size = self.config.hidden_size
        self.embed_dim = self.config.embed_dim
        self.query_key = self.config.query_key
        self.embedding_key = self.config.embedding_key
        self.out_key = self.config.out_key

        self.bias = nn.Parameter(torch.Tensor(1).to(dtype=torch.float32))
        self._init_weights()

    def _init_weights(self):
        """Kaiming (He) initialization for bias"""
        if self.bias is not None:
            # The input to this layer is the query dim
            bound = 1 / math.sqrt(self.embed_dim)
            nn.init.uniform_(self.bias, -bound, bound)

    def forward(self, td: TensorDict):
        query = td[self.query_key]  # Shape: [B*TT, embed_dim]
        action_embeds = td[self.embedding_key]  # Shape: [B*TT, num_actions, embed_dim]

        # Compute scores
        scores = torch.einsum("b e, b a e -> b a", query, action_embeds)  # Shape: [B*TT, num_actions]

        # Add bias
        biased_scores = scores + self.bias  # Shape: [B*TT, num_actions]

        td[self.out_key] = biased_scores
        return td


class ActionProbsConfig(ComponentConfig):
    model_config = ConfigDict(extra="ignore")

    in_key: str
    action_column: int = 0
    actions_key: str = "actions"
    act_log_prob_key: str = "act_log_prob"
    entropy_key: str = "entropy"
    full_log_probs_key: str = "full_log_probs"
    vibe_in_key: Optional[str] = None
    vibe_action_column: int = 1
    vibe_actions_key: str = "vibe_actions"
    vibe_act_log_prob_key: str = "vibe_act_log_prob"
    vibe_entropy_key: str = "vibe_entropy"
    vibe_full_log_probs_key: str = "vibe_full_log_probs"
    name: str = "action_probs"

    def make_component(self, env=None):
        return ActionProbs(config=self)


class ActionProbs(nn.Module):
    """
    Computes action scores based on a query and action embeddings (keys).
    """

    def __init__(self, config: ActionProbsConfig):
        super().__init__()
        self.config = config
        self.num_actions = 0
        self.num_vibe_actions = 0

    def _ensure_initialized(self) -> None:
        if self.num_actions <= 0:
            raise RuntimeError("ActionProbs not initialized; call initialize_to_environment before forward.")

    def initialize_to_environment(
        self,
        env: PolicyEnvInterface,
        device: torch.device,
    ) -> None:
        action_space = env.action_space
        if not isinstance(action_space, Discrete):
            msg = f"ActionProbs expects a Discrete action space, got {type(action_space).__name__}"
            raise TypeError(msg)

        self.num_actions = int(action_space.n)
        self.num_vibe_actions = len(env.vibe_action_names)

    def _select_action_indices(
        self,
        *,
        action: torch.Tensor,
        column: int,
        td: TensorDict,
        fallback_key: str,
    ) -> torch.Tensor:
        if action.dim() == 1:
            if column == 0:
                return action.to(dtype=torch.long)
            if fallback_key in td:
                return td[fallback_key].reshape(-1).to(dtype=torch.long)
            raise ValueError(f"Expected action column {column}, but action shape is {tuple(action.shape)}")

        if action.dim() == 2:
            if action.size(1) > column:
                return action[:, column].to(dtype=torch.long)
            if fallback_key in td:
                return td[fallback_key].reshape(-1).to(dtype=torch.long)
            raise ValueError(f"Expected action column {column}, but action shape is {tuple(action.shape)}")

        raise ValueError(f"Expected 1D or 2D action tensor, got shape {tuple(action.shape)}")

    def _mask_logits_if_needed(self, logits: torch.Tensor) -> torch.Tensor:
        """Sanitize logits and mask past the first 21 actions (keep full action_dim for checkpoint compatibility)."""
        mask_value = -1e9
        logits = torch.nan_to_num(logits, nan=mask_value, posinf=mask_value, neginf=mask_value)
        if logits.size(-1) > 21:
            logits = logits.clone()
            logits[..., 21:] = mask_value
        return logits

    def forward(self, td: TensorDict, action: Optional[torch.Tensor] = None) -> TensorDict:
        return self.forward_inference(td) if action is None else self.forward_training(td, action)

    def forward_inference(self, td: TensorDict) -> TensorDict:
        """Forward pass for inference mode with action sampling."""
        logits = td[self.config.in_key]

        self._ensure_initialized()
        logits = self._mask_logits_if_needed(logits)
        action_logit_index, selected_log_probs, _, full_log_probs = sample_actions(logits)

        td[self.config.actions_key] = action_logit_index.to(dtype=torch.int32)
        td[self.config.act_log_prob_key] = selected_log_probs
        td[self.config.full_log_probs_key] = full_log_probs

        if self.config.vibe_in_key and self.num_vibe_actions > 0:
            vibe_logits = td[self.config.vibe_in_key]
            vibe_logits = self._mask_logits_if_needed(vibe_logits)
            vibe_actions, vibe_log_probs, _, vibe_full_log_probs = sample_actions(vibe_logits)
            td[self.config.vibe_actions_key] = vibe_actions.to(dtype=torch.int32)
            td[self.config.vibe_act_log_prob_key] = vibe_log_probs
            td[self.config.vibe_full_log_probs_key] = vibe_full_log_probs

        return td

    def forward_training(self, td: TensorDict, action: torch.Tensor) -> TensorDict:
        """Forward pass for training mode with proper TD reshaping."""
        # CRITICAL: ComponentPolicy expects the action to be flattened already during training
        # The TD should be reshaped to match the flattened batch dimension
        logits = td[self.config.in_key]
        if action.dim() == 3:
            batch_size_orig, time_steps, _ = action.shape
            action = action.view(batch_size_orig * time_steps, -1)
            # Also flatten the TD to match
            if td.batch_dims > 1:
                td = td.reshape(td.batch_size.numel())
        self._ensure_initialized()
        logits = self._mask_logits_if_needed(logits)
        action_logit_index = self._select_action_indices(
            action=action,
            column=self.config.action_column,
            td=td,
            fallback_key=self.config.actions_key,
        )
        selected_log_probs, entropy, action_log_probs = evaluate_actions(logits, action_logit_index)

        # Store in flattened TD (will be reshaped by caller if needed)
        td[self.config.act_log_prob_key] = selected_log_probs
        td[self.config.entropy_key] = entropy
        td[self.config.full_log_probs_key] = action_log_probs

        if self.config.vibe_in_key and self.num_vibe_actions > 0:
            vibe_logits = td[self.config.vibe_in_key]
            vibe_logits = self._mask_logits_if_needed(vibe_logits)
            vibe_action_index = self._select_action_indices(
                action=action,
                column=self.config.vibe_action_column,
                td=td,
                fallback_key=self.config.vibe_actions_key,
            )
            vibe_log_probs, vibe_entropy, vibe_full_log_probs = evaluate_actions(vibe_logits, vibe_action_index)
            td[self.config.vibe_act_log_prob_key] = vibe_log_probs
            td[self.config.vibe_entropy_key] = vibe_entropy
            td[self.config.vibe_full_log_probs_key] = vibe_full_log_probs

        # ComponentPolicy reshapes the TD after training forward based on td["batch"] and td["bptt"]
        # The reshaping happens in ComponentPolicy.forward() after forward_training()
        return td


class ActorHeadConfig(ComponentConfig):
    in_key: str
    out_key: str
    input_dim: int
    layer_init_std: float = 1.0
    action_space: Literal["non_vibe", "vibe"] = "non_vibe"
    name: str = "actor_head"

    def make_component(self, env: PolicyEnvInterface):
        return ActorHead(config=self, env=env)


class ActorHead(nn.Module):
    """Simple linear head that maps hidden features to environment logits."""

    def __init__(self, config: ActorHeadConfig, env: PolicyEnvInterface):
        super().__init__()
        self.config = config
        self.in_key = self.config.in_key
        self.out_key = self.config.out_key
        if self.config.action_space == "non_vibe":
            self.num_actions = int(env.action_space.n)
        elif self.config.action_space == "vibe":
            self.num_actions = len(env.vibe_action_names)
        else:
            raise ValueError(f"Unsupported action_space setting: {self.config.action_space}")
        if self.num_actions <= 0:
            raise ValueError(f"Actor head '{self.out_key}' requires at least one action")

        linear = pufferlib.pytorch.layer_init(
            nn.Linear(self.config.input_dim, self.num_actions),
            std=self.config.layer_init_std,
        )
        self._module = TDM(linear, in_keys=[self.in_key], out_keys=[self.out_key])

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
        """Pad actor_head weights/bias if checkpoint has fewer actions than env."""
        weight_key = prefix + "_module.module.weight"
        bias_key = prefix + "_module.module.bias"

        weight = state_dict.get(weight_key)
        bias = state_dict.get(bias_key)

        if weight is not None and bias is not None and weight.shape[0] < self.num_actions:
            pad = self.num_actions - weight.shape[0]
            # Pad weights with zeros; pad biases with -inf to keep zero prob.
            weight_pad = torch.zeros(pad, weight.shape[1], dtype=weight.dtype, device=weight.device)
            bias_pad = torch.full((pad,), -1e9, dtype=bias.dtype, device=bias.device)
            state_dict[weight_key] = torch.cat([weight, weight_pad], dim=0)
            state_dict[bias_key] = torch.cat([bias, bias_pad], dim=0)

        module_strict = strict
        if self.config.action_space == "vibe" and (weight is None or bias is None):
            module_strict = False

        super()._load_from_state_dict(
            state_dict,
            prefix,
            local_metadata,
            module_strict,
            missing_keys,
            unexpected_keys,
            error_msgs,
        )

    def forward(self, td: TensorDict) -> TensorDict:
        return self._module(td)
