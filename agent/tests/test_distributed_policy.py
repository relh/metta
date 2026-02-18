from __future__ import annotations

from typing import Optional

import torch
from tensordict import TensorDict

from metta.agent.policy import DistributedPolicy, Policy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


def _make_policy_env_info() -> PolicyEnvInterface:
    from mettagrid.config.mettagrid_config import MettaGridConfig  # noqa: PLC0415

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


def test_distributed_policy_disables_find_unused_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured_kwargs: dict[str, object] = {}

    def fake_ddp_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        object.__setattr__(self, "module", kwargs["module"])

    monkeypatch.setattr("metta.agent.policy.DistributedDataParallel.__init__", fake_ddp_init)
    env_info = _make_policy_env_info()
    policy = _SimplePolicy(env_info)
    DistributedPolicy(policy, torch.device("cpu"))

    assert captured_kwargs["find_unused_parameters"] is False
