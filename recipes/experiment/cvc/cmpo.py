"""CMPO Cogsguard training entry points (legacy CVC wrapper)."""

from __future__ import annotations

from typing import Literal, Optional, Sequence

import metta.tools as tools
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from metta.rl.training.teacher import TeacherConfig
from recipes.experiment import cogsguard
from recipes.experiment.losses.cmpo import cmpo_losses

_CogsGuardLayout = Literal["machina_1", "arena"]


def train(
    num_cogs: int = 4,
    max_steps: int = 10000,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    variants: Optional[str | Sequence[str]] = None,
    layout: _CogsGuardLayout = "machina_1",
    sweep_mode: bool = False,
    use_clips_curriculum: bool = False,
) -> tools.TrainTool:
    resolved_curriculum = curriculum
    if resolved_curriculum is None and not use_clips_curriculum:
        env = cogsguard.make_env(num_agents=num_cogs, max_steps=max_steps, variants=variants, layout=layout)
        resolved_curriculum = cogsguard.make_curriculum(env=env, variants=variants, layout=layout)
    tool = cogsguard.train(
        curriculum=resolved_curriculum,
        policy_architecture=policy_architecture,
        teacher=teacher,
        variants=variants,
        layout=layout,
        sweep_mode=sweep_mode,
        use_clips_curriculum=use_clips_curriculum,
    )
    tool.trainer.losses = cmpo_losses()
    return tool


__all__ = ["train"]
