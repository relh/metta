"""Single-mission Cogsguard entry points (legacy CVC wrapper)."""

from __future__ import annotations

from typing import Literal, Optional, Sequence

import metta.cogworks.curriculum as cc
import metta.tools as tools
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from metta.rl.training.teacher import TeacherConfig
from metta.sim.simulation_config import SimulationConfig
from recipes.experiment import cogsguard

_CogsGuardLayout = Literal["machina_1", "arena"]


def train(
    num_cogs: int = 4,
    max_steps: int = 10000,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    variants: Optional[str | Sequence[str]] = None,
    layout: _CogsGuardLayout = "machina_1",
    use_default_teacher: bool = False,
    sweep_mode: bool = False,
    use_clips_curriculum: bool = False,
) -> tools.TrainTool:
    resolved_curriculum = curriculum
    if resolved_curriculum is None and not use_clips_curriculum:
        env = cogsguard.make_env(num_agents=num_cogs, max_steps=max_steps, variants=variants, layout=layout)
        resolved_curriculum = cc.env_curriculum(env)
    return cogsguard.train(
        curriculum=resolved_curriculum,
        policy_architecture=policy_architecture,
        teacher=teacher,
        variants=variants,
        layout=layout,
        use_default_teacher=use_default_teacher,
        sweep_mode=sweep_mode,
        use_clips_curriculum=use_clips_curriculum,
    )


def play(
    policy_uri: Optional[str] = None,
    num_cogs: int = 4,
    max_steps: int = 10000,
    variants: Optional[str | Sequence[str]] = None,
    layout: _CogsGuardLayout = "machina_1",
) -> tools.PlayTool:
    env = cogsguard.make_env(num_agents=num_cogs, max_steps=max_steps, variants=variants, layout=layout)
    sim = SimulationConfig(suite="cogsguard", name=f"basic_{layout}", env=env)
    return tools.PlayTool(sim=sim, policy_uri=policy_uri)


__all__ = ["train", "play"]
