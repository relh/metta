from __future__ import annotations

import logging
from typing import Optional

import metta.tools as tools
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from recipes.experiment.abes._mamba_recipe_utils import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_FORWARD_PASS_MINIBATCH_TARGET_SIZE,
    DEFAULT_LEARNING_RATE,
    DEFAULT_MINIBATCH_SIZE,
    apply_training_overrides,
    ensure_cuda_extras_installed,
    supports_mem_eff_path,
)
from recipes.prod.arena_basic_easy_shaped import (
    evaluate,
    evaluate_in_sweep,
    make_curriculum,
    mettagrid,
    play,
    replay,
    simulations,
    sweep,
)
from recipes.prod.arena_basic_easy_shaped import (
    train as base_train,
)

logger = logging.getLogger(__name__)


def train(
    *,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: PolicyArchitecture | None = None,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    minibatch_size: int = DEFAULT_MINIBATCH_SIZE,
    forward_pass_minibatch_target_size: int = DEFAULT_FORWARD_PASS_MINIBATCH_TARGET_SIZE,
) -> tools.TrainTool:
    ensure_cuda_extras_installed(logger)

    try:
        from metta.agent.components.drama.config import DramaWorldModelConfig  # noqa: PLC0415
        from metta.agent.policies.drama_policy import DramaPolicyConfig  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        if exc.name == "mamba_ssm":
            raise RuntimeError(
                "DRAMA recipes require the `mamba-ssm` package (Linux + CUDA)."
                " Install it on a supported system before running this recipe."
            ) from exc
        raise

    policy = policy_architecture or DramaPolicyConfig()

    mem_eff_supported = supports_mem_eff_path()
    if not mem_eff_supported:
        logger.warning(
            "[ABES Drama] Detected missing causal-conv1d CUDA kernels; disabling memory-efficient path."
            " Install `flash-attn` and `causal-conv1d` for best performance."
        )

    for component in policy.components:
        if isinstance(component, DramaWorldModelConfig):
            ssm_cfg = dict(component.ssm_cfg) if component.ssm_cfg else {}
            if not mem_eff_supported:
                ssm_cfg["use_mem_eff_path"] = False
            component.ssm_cfg = ssm_cfg

    tool = base_train(
        curriculum=curriculum,
        policy_architecture=policy,
    )

    apply_training_overrides(
        tool,
        learning_rate=learning_rate,
        batch_size=batch_size,
        minibatch_size=minibatch_size,
        forward_pass_minibatch_target_size=forward_pass_minibatch_target_size,
    )

    return tool


__all__ = [
    "mettagrid",
    "make_curriculum",
    "simulations",
    "play",
    "replay",
    "evaluate",
    "evaluate_in_sweep",
    "sweep",
    "train",
]
