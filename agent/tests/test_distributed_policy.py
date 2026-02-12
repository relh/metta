from __future__ import annotations

from typing import Optional

import torch
from cortex.routed_adapter import RoutedAdapterLinear
from tensordict import TensorDict

from metta.agent.policy import DistributedPolicy, Policy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


def _make_policy_env_info() -> PolicyEnvInterface:
    from mettagrid.config import MettaGridConfig  # noqa: PLC0415

    return PolicyEnvInterface.from_mg_cfg(MettaGridConfig())


class _SimplePolicy(Policy):
    def __init__(self, policy_env_info: PolicyEnvInterface) -> None:
        super().__init__(policy_env_info)
        self.linear = torch.nn.Linear(4, 4)
        self._device = torch.device("cpu")

    def forward(self, td: TensorDict, action: Optional[torch.Tensor] = None) -> TensorDict:
        return td

    @property
    def device(self) -> torch.device:
        return self._device

    def reset_memory(self) -> None:
        pass


class _RoutedPolicy(_SimplePolicy):
    def __init__(self, policy_env_info: PolicyEnvInterface) -> None:
        super().__init__(policy_env_info)
        self.routed = RoutedAdapterLinear(
            in_features=4,
            out_features=4,
            bias=True,
            num_slots=2,
            rank=2,
            require_route_ids=False,
        )


def test_distributed_policy_detects_routed_adapters() -> None:
    env_info = _make_policy_env_info()

    assert DistributedPolicy._uses_routed_adapters(_RoutedPolicy(env_info))
    assert not DistributedPolicy._uses_routed_adapters(_SimplePolicy(env_info))
