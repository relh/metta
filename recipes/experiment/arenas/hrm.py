"""Arena recipe with HRM policy architecture."""

from metta.agent.policies.hrm import HRMTinyConfig
from metta.agent.policy import PolicyArchitecture
from metta.rl.policy_assets import PolicyAssetConfig
from recipes.experiment import arena as base

mettagrid = base.mettagrid
make_curriculum = base.make_curriculum
simulations = base.simulations
play = base.play
replay = base.replay
evaluate = base.evaluate


def train(
    *,
    curriculum=None,
    policy_architecture: PolicyArchitecture | None = None,
):
    """Train with HRM policy architecture (defaults to HRMTinyConfig for memory efficiency)."""
    tool = base.train(
        curriculum=curriculum,
    )
    tool.policy_assets["learner0"] = PolicyAssetConfig(architecture=policy_architecture or HRMTinyConfig())
    return tool


def train_shaped(
    rewards: bool = True,
    policy_architecture: PolicyArchitecture | None = None,
):
    """Train with HRM policy architecture using shaped rewards (defaults to HRMTinyConfig)."""
    tool = base.train_shaped(rewards=rewards)
    tool.policy_assets["learner0"] = PolicyAssetConfig(architecture=policy_architecture or HRMTinyConfig())
    return tool


__all__ = [
    "mettagrid",
    "make_curriculum",
    "simulations",
    "play",
    "replay",
    "evaluate",
    "train",
    "train_shaped",
]
