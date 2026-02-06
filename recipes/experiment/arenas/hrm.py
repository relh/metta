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
    enable_detailed_slice_logging: bool = False,
    policy_architecture: PolicyArchitecture | None = None,
):
    """Train with HRM policy architecture (defaults to HRMTinyConfig for memory efficiency)."""
    tool = base.train(
        curriculum=curriculum,
        enable_detailed_slice_logging=enable_detailed_slice_logging,
    )
    # Update policy architecture
    resolved_arch = policy_architecture or HRMTinyConfig()
    learner_cfg = tool.policy_assets.get("learner0")
    if learner_cfg is None:
        tool.policy_assets["learner0"] = PolicyAssetConfig(architecture=resolved_arch)
    else:
        learner_cfg.architecture = resolved_arch
    return tool


def train_shaped(
    rewards: bool = True,
    converters: bool = True,
    policy_architecture: PolicyArchitecture | None = None,
):
    """Train with HRM policy architecture using shaped rewards (defaults to HRMTinyConfig)."""
    tool = base.train_shaped(rewards=rewards, converters=converters)
    # Update policy architecture
    resolved_arch = policy_architecture or HRMTinyConfig()
    learner_cfg = tool.policy_assets.get("learner0")  # this recipe assumes a single trainable policy
    if learner_cfg is None:
        tool.policy_assets["learner0"] = PolicyAssetConfig(architecture=resolved_arch)
    else:
        learner_cfg.architecture = resolved_arch
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
