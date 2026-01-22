"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from typing import Optional, Sequence

import metta.cogworks.curriculum as cc
from cogames.cogs_vs_clips.cogsguard_reward_variants import apply_reward_variants
from cogames.cogs_vs_clips.missions import make_cogsguard_mission
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import (
    CurriculumAlgorithmConfig,
    CurriculumConfig,
    DiscreteRandomConfig,
)
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
    max_steps: int = 1000,
    variants: str | Sequence[str] | None = None,
) -> MettaGridConfig:
    """Create a CogsGuard environment."""
    env = make_cogsguard_mission(num_agents, max_steps).make_env()
    apply_reward_variants(env, variants=variants)
    return env


def make_curriculum(
    env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
    variants: str | Sequence[str] | None = None,
) -> CurriculumConfig:
    env = env or make_env(variants=variants)

    tasks = cc.bucketed(env)

    # for item in ["ore_red", "battery_red", "laser", "armor"]:
    #     arena_tasks.add_bucket(f"game.agent.rewards.inventory.{item}", [0, 0.1, 0.5, 0.9, 1.0])
    #     arena_tasks.add_bucket(f"game.agent.rewards.inventory_max.{item}", [1, 2])

    # enable or disable attacks. we use cost instead of 'enabled'
    # to maintain action space consistency.
    # tasks.add_bucket("game.max_steps", [1000, 5000, 10000])
    tasks.add_bucket("game.agent.inventory.initial.heart", [0, 1, 2, 3])

    if algorithm_config is None:
        # algorithm_config = LearningProgressConfig(
        #     use_bidirectional=True,
        #     ema_timescale=0.001,
        #     exploration_bonus=0.1,
        #     max_memory_tasks=2000,
        #     max_slice_axes=4,
        #     enable_detailed_slice_logging=True,
        # )
        algorithm_config = DiscreteRandomConfig()

    return tasks.to_curriculum(algorithm_config=algorithm_config)


def simulations(
    env: Optional[MettaGridConfig] = None,
    variants: str | Sequence[str] | None = None,
) -> list[SimulationConfig]:
    env = env or make_env(variants=variants)

    return [
        SimulationConfig(suite="cogsguard", name="basic", env=env),
    ]


def train(
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    variants: str | Sequence[str] | None = None,
) -> TrainTool:
    return train_single_mission(
        curriculum=curriculum,
        policy_architecture=policy_architecture,
        teacher=teacher,
        variants=variants,
    )


def train_single_mission(
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    variants: str | Sequence[str] | None = None,
) -> TrainTool:
    from metta.agent.policies.vit import ViTDefaultConfig

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
    variants: str | Sequence[str] | None = None,
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


def play(policy_uri: Optional[str] = None, variants: str | Sequence[str] | None = None) -> PlayTool:
    """Interactive play with a policy."""
    return PlayTool(sim=simulations(variants=variants)[0], policy_uri=policy_uri)


def replay(policy_uri: Optional[str] = None, variants: str | Sequence[str] | None = None) -> ReplayTool:
    """Generate replay from a policy."""
    return ReplayTool(sim=simulations(variants=variants)[0], policy_uri=policy_uri)
