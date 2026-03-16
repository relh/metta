import logging
from collections import OrderedDict
from contextlib import ExitStack
from typing import Any, Optional, cast

import torch
from tensordict import TensorDict
from tensordict.nn import TensorDictSequential
from torch.nn.parameter import UninitializedParameter
from torchrl.data import Composite, UnboundedDiscrete

from metta.agent.policy import Policy, PolicyArchitecture
from metta.agent.util.torch_backends import build_sdpa_context
from mettagrid.base_config import Config
from mettagrid.policy.policy_env_interface import PolicyEnvInterface

logger = logging.getLogger("metta_agent")


def log_on_master_with_level(log_level: int, *args, **argv) -> None:
    if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
        logger.log(log_level, *args, **argv)


class PolicyAutoBuilder(Policy):
    """Generic policy builder for use with configs."""

    def __init__(self, policy_env_info: PolicyEnvInterface, config: Config | None = None):
        super().__init__(policy_env_info)
        self.config = config

        self.components = OrderedDict()
        if self.config is not None and isinstance(self.config, PolicyArchitecture):
            for component_config in self.config.components:
                name = component_config.name
                self.components[name] = component_config.make_component(policy_env_info)
            self.action_probs = self.config.action_probs_config.make_component()

        self._sequential_network = TensorDictSequential(self.components, inplace=True)
        self._sdpa_context = ExitStack()

        self._total_params = sum(
            param.numel()
            for param in self.parameters()
            if param.requires_grad and not isinstance(param, UninitializedParameter)
        )

    def forward(self, td: TensorDict, action: Optional[torch.Tensor] = None) -> TensorDict:
        td = self._sequential_network(td)
        self.action_probs(td, action)
        # Only flatten values if they exist (GRPO policies don't have critic networks)
        if "values" in td:
            td["values"] = td["values"].flatten()
        if "h_values" in td:
            td["h_values"] = td["h_values"].flatten()
        return td

    def initialize_to_environment(
        self,
        policy_env_info: PolicyEnvInterface,
        device: torch.device,
    ):
        self.to(device)
        self._sdpa_context.close()
        self._sdpa_context = ExitStack()
        if torch.cuda.is_available():
            context = build_sdpa_context()
            if context is not None:
                self._sdpa_context.enter_context(context)
        logs = []
        for value in self.components.values():
            initialize = getattr(value, "initialize_to_environment", None)
            if callable(initialize):
                logs.append(initialize(policy_env_info, device))
        initialize_action_probs = getattr(self.action_probs, "initialize_to_environment", None)
        if callable(initialize_action_probs):
            initialize_action_probs(policy_env_info, device)

        for log in logs:
            if log is not None:
                log_on_master_with_level(logging.DEBUG, log)

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["_sdpa_context"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)  # type: ignore
        self._sdpa_context = ExitStack()

    def reset_memory(self):
        for value in self.components.values():
            reset_memory = getattr(value, "reset_memory", None)
            if callable(reset_memory):
                reset_memory()

    @property
    def total_params(self):
        return self._total_params

    def get_agent_experience_spec(self) -> Composite:
        spec = Composite(
            env_obs=UnboundedDiscrete(shape=torch.Size([200, 3]), dtype=torch.uint8),
        )
        for layer in self.components.values():
            get_agent_experience_spec = getattr(layer, "get_agent_experience_spec", None)
            if callable(get_agent_experience_spec):
                spec.update(cast(Composite, get_agent_experience_spec()))

        return spec

    def network(self) -> torch.nn.Module:
        """Return the sequential component stack used for inference and training."""
        return self._sequential_network

    @property
    def device(self) -> torch.device:
        return next(self.parameters()).device
