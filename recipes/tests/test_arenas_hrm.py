from __future__ import annotations

from metta.agent.policies.hrm import HRMPolicyConfig, HRMTinyConfig
from recipes.experiment.arenas import hrm


def test_hrm_train_defaults_to_tiny_architecture() -> None:
    tool = hrm.train()
    assert isinstance(tool.policy_assets["learner0"].architecture, HRMTinyConfig)


def test_hrm_train_uses_explicit_architecture() -> None:
    custom_arch = HRMPolicyConfig()
    tool = hrm.train(policy_architecture=custom_arch)
    assert tool.policy_assets["learner0"].architecture is custom_arch


def test_hrm_train_shaped_uses_explicit_architecture() -> None:
    custom_arch = HRMPolicyConfig()
    tool = hrm.train_shaped(policy_architecture=custom_arch)
    assert tool.policy_assets["learner0"].architecture is custom_arch
