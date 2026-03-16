from __future__ import annotations

import pytest
import torch
from torch import nn

from metta.agent.policy import ExternalPolicyWrapper, _module_name_for_spec
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class _DummyPolicy(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.linear = nn.Linear(3, 2)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        return self.linear(obs)


class _ParameterlessPolicy(nn.Module):
    def forward(self, obs: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        return obs


def _make_policy_env_info() -> PolicyEnvInterface:
    from mettagrid.config.mettagrid_config import MettaGridConfig  # noqa: PLC0415

    return PolicyEnvInterface.from_mg_cfg(MettaGridConfig())


def test_external_policy_wrapper_is_module() -> None:
    wrapper = ExternalPolicyWrapper(_DummyPolicy(), _make_policy_env_info())

    # These nn.Module helpers should work without raising AttributeError
    wrapper.train()
    wrapper.eval()
    wrapper.to(torch.device("cpu"))

    assert isinstance(wrapper.policy, nn.Module)


def test_external_policy_wrapper_defaults_to_cpu_for_parameterless_modules() -> None:
    wrapper = ExternalPolicyWrapper(_ParameterlessPolicy(), _make_policy_env_info())

    assert wrapper.device == torch.device("cpu")


def test_module_name_for_spec_rejects_non_importable_file_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DetachedArchitecture:
        pass

    monkeypatch.setattr(_DetachedArchitecture, "__module__", "/tmp/detached_policy.py")

    with pytest.raises(ValueError, match="non-importable module path"):
        _module_name_for_spec(_DetachedArchitecture)
