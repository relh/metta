"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from typing import Optional, Sequence

import metta.cogworks.curriculum as cc
from cogames.cogs_vs_clips.cogsguard_reward_variants import apply_reward_variants
from cogames.cogs_vs_clips.missions import make_cogsguard_mission
from metta.agent.policies.vit import ViTDefaultConfig
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import (
    CurriculumAlgorithmConfig,
    CurriculumConfig,
    DiscreteRandomConfig,
)
from metta.cogworks.curriculum.learning_progress_algorithm import LearningProgressConfig
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.rl.training.scheduler import LossRunGate, SchedulerConfig, ScheduleRule
from metta.rl.training.teacher import TeacherConfig, apply_teacher_phase
from metta.sim.simulation_config import SimulationConfig
from metta.tools.eval import EvaluateTool
from metta.tools.play import PlayTool
from metta.tools.replay import ReplayTool
from metta.tools.train import TrainTool
from mettagrid.config.mettagrid_config import MettaGridConfig


def make_env(
    num_agents: int = 10,
    max_steps: int = 10000,
    variants: Sequence[str] | None = None,
) -> MettaGridConfig:
    """Create a CogsGuard environment."""
    variants = variants or ["objective"]
    env = make_cogsguard_mission(num_agents, max_steps).make_env()
    apply_reward_variants(env, variants=variants)
    return env


def make_curriculum(
    env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
    variants: Sequence[str] | None = None,
) -> CurriculumConfig:
    variant_list = list(variants) if variants else ["objective"]

    if variant_list:
        task_generators = []
        for variant in variant_list:
            env_variant = make_env(variants=[variant])
            tasks_cfg = cc.bucketed(env_variant)
            task_generators.append(tasks_cfg)

        merged_tasks = cc.merge(task_generators) if len(task_generators) > 1 else task_generators[0]
        algorithm_config = algorithm_config or LearningProgressConfig()
        return merged_tasks.to_curriculum(algorithm_config=algorithm_config)

    env = env or make_env(variants=None)
    tasks = cc.bucketed(env)

    if algorithm_config is None:
        algorithm_config = DiscreteRandomConfig()

    return tasks.to_curriculum(algorithm_config=algorithm_config)


def simulations(
    env: Optional[MettaGridConfig] = None,
    variants: Sequence[str] | None = None,
) -> list[SimulationConfig]:
    selected_variant = list(variants)[0] if variants else "objective"

    env = env or make_env(variants=[selected_variant] if selected_variant is not None else None)

    return [
        SimulationConfig(suite="cogsguard", name="basic", env=env),
    ]


def train(
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    variants: Sequence[str] | None = None,
    use_default_teacher: bool = False,
) -> TrainTool:
    if teacher is None and use_default_teacher:
        teacher = TeacherConfig(
            mode="supervisor",
            policy_uri="metta://policy/pinky",
            steps=5_500_000_000,
            teacher_led_proportion=0.0,
            anneal_start_step=2_500_000_000,
            ppo_begin_step=0,
        )

    resolved_curriculum = curriculum or make_curriculum(variants=variants)
    trainer_cfg = TrainerConfig()
    training_env_cfg = TrainingEnvironmentConfig(curriculum=resolved_curriculum)
    evaluator_cfg = EvaluatorConfig(simulations=simulations(variants=variants))
    scheduler = None

    if teacher and teacher.enabled:
        scheduler_run_gates: list[LossRunGate] = []
        scheduler_rules: list[ScheduleRule] = []
        apply_teacher_phase(
            trainer_cfg=trainer_cfg,
            training_env_cfg=training_env_cfg,
            scheduler_rules=scheduler_rules,
            scheduler_run_gates=scheduler_run_gates,
            teacher_cfg=teacher,
        )
        scheduler = SchedulerConfig(run_gates=scheduler_run_gates, rules=scheduler_rules)

    tt = TrainTool(
        trainer=trainer_cfg,
        training_env=training_env_cfg,
        evaluator=evaluator_cfg,
        scheduler=scheduler,
    )
    tt.stats_reporter.progress_metric = "env_collective/cogs/aligned.junction.held"
    tt.stats_reporter.default_zero_metrics = tt.stats_reporter.default_zero_metrics + (
        "env_collective/cogs/aligned.junction.held",
    )
    tt.policy_architecture = policy_architecture or ViTDefaultConfig(obs_shim_ignore_inventory_power_tokens=False)
    return tt


def evaluate(
    policy_uris: str | Sequence[str] | None = None,
    variants: Sequence[str] | None = None,
) -> EvaluateTool:
    resolved_policy_uris: str | list[str]
    if policy_uris is None:
        resolved_policy_uris = []
    elif isinstance(policy_uris, str):
        resolved_policy_uris = policy_uris
    else:
        resolved_policy_uris = list(policy_uris)
    return EvaluateTool(
        simulations=simulations(variants=variants),
        policy_uris=resolved_policy_uris,
    )


def play(policy_uri: Optional[str] = None, variants: Sequence[str] | None = None) -> PlayTool:
    """Interactive play with a policy."""
    return PlayTool(sim=simulations(variants=variants)[0], policy_uri=policy_uri)


def replay(policy_uri: Optional[str] = None, variants: Sequence[str] | None = None) -> ReplayTool:
    """Generate replay from a policy."""
    return ReplayTool(sim=simulations(variants=variants)[0], policy_uri=policy_uri)
