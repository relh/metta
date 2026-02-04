"""Machina 1 layout wrappers over Cogsguard training."""

from __future__ import annotations

from typing import Optional, Sequence

import metta.tools as tools
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from metta.rl.training.teacher import TeacherConfig
from metta.sim.simulation_config import SimulationConfig
from mettagrid.config import vibes
from recipes.experiment import cogsguard


def _apply_full_vibes(env_cfg) -> None:
    env_cfg.game.vibe_names = [v.name for v in vibes.VIBES]
    change_vibe = getattr(env_cfg.game.actions, "change_vibe", None)
    if change_vibe is not None:
        change_vibe.vibes = list(vibes.VIBES)
    if env_cfg.game.agent.vibe >= len(vibes.VIBES):
        env_cfg.game.agent.vibe = 0


def _resolve_curriculum(
    curriculum: Optional[CurriculumConfig],
    *,
    num_cogs: int,
    max_steps: int,
    variants: Optional[Sequence[str]],
    use_clips_curriculum: bool,
) -> Optional[CurriculumConfig]:
    if curriculum is not None or use_clips_curriculum:
        return curriculum
    env_cfg = cogsguard.make_env(
        num_agents=num_cogs,
        max_steps=max_steps,
        variants=variants,
        layout="machina_1",
    )
    _apply_full_vibes(env_cfg)
    return cogsguard.make_curriculum(env=env_cfg, variants=variants, layout="machina_1")


def _make_simulation(
    *,
    num_cogs: int,
    max_steps: int,
    variants: Optional[Sequence[str]],
) -> SimulationConfig:
    env_cfg = cogsguard.make_env(
        num_agents=num_cogs,
        max_steps=max_steps,
        variants=variants,
        layout="machina_1",
    )
    _apply_full_vibes(env_cfg)
    return SimulationConfig(suite="cogsguard", name="basic_machina_1", env=env_cfg)


def train(
    num_cogs: int = 4,
    max_steps: int = 10000,
    curriculum: Optional[CurriculumConfig] = None,
    variants: Optional[Sequence[str]] = None,
    eval_variants: Optional[Sequence[str]] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    use_default_teacher: bool = False,
    use_clips_curriculum: bool = False,
) -> tools.TrainTool:
    resolved_curriculum = _resolve_curriculum(
        curriculum,
        num_cogs=num_cogs,
        max_steps=max_steps,
        variants=variants,
        use_clips_curriculum=use_clips_curriculum,
    )

    tt = cogsguard.train(
        curriculum=resolved_curriculum,
        policy_architecture=policy_architecture,
        teacher=teacher,
        variants=variants,
        layout="machina_1",
        use_default_teacher=use_default_teacher,
        use_clips_curriculum=use_clips_curriculum,
    )
    tt.system.torch_deterministic = False

    resolved_eval_variants = eval_variants if eval_variants is not None else variants
    tt.evaluator.simulations = [
        _make_simulation(
            num_cogs=num_cogs,
            max_steps=max_steps,
            variants=resolved_eval_variants,
        )
    ]
    tt.evaluator.epoch_interval = 150
    return tt


def play(
    policy_uri: Optional[str] = None,
    num_cogs: int = 4,
    max_steps: int = 10000,
    variants: Optional[Sequence[str]] = None,
) -> tools.PlayTool:
    return tools.PlayTool(
        sim=_make_simulation(num_cogs=num_cogs, max_steps=max_steps, variants=variants),
        policy_uri=policy_uri,
    )


def replay(
    policy_uri: Optional[str] = None,
    num_cogs: int = 4,
    max_steps: int = 10000,
    variants: Optional[Sequence[str]] = None,
) -> tools.ReplayTool:
    return tools.ReplayTool(
        sim=_make_simulation(num_cogs=num_cogs, max_steps=max_steps, variants=variants),
        policy_uri=policy_uri,
    )


def train_sweep(
    variants: Optional[Sequence[str]] = ("milestones", "credit"),
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    use_default_teacher: bool = False,
) -> tools.TrainTool:
    tool = cogsguard.train_sweep(
        variants=variants,
        layout="machina_1",
        policy_architecture=policy_architecture,
        teacher=teacher,
        use_default_teacher=use_default_teacher,
    )
    tool.trainer.total_timesteps = 1_000_000_000
    return tool


def evaluate_stub(*args: object, **kwargs: object) -> tools.StubTool:
    return tools.StubTool()


def sweep(
    sweep_name: str,
    variants: Optional[Sequence[str]] = ("milestones", "credit"),
    sweep_reward_variants: bool = True,
    max_trials: int = 80,
    num_parallel_trials: int = 4,
) -> tools.SweepTool:
    return cogsguard.sweep(
        sweep_name=sweep_name,
        variants=variants,
        sweep_reward_variants=sweep_reward_variants,
        max_trials=max_trials,
        num_parallel_trials=num_parallel_trials,
    )
