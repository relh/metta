"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from typing import Literal, Optional, Sequence

import metta.cogworks.curriculum as cc
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
from mettagrid.config.mettagrid_config import AgentRewards, MettaGridConfig

RewardPreset = Literal["credit", "milestones", "objective"]


def _reward_preset_objective(*, max_steps: int) -> AgentRewards:
    return AgentRewards(
        collective_stats={
            "aligned.junction.held": 1.0 / max_steps,
        },
    )


def _reward_preset_milestones(*, max_steps: int) -> AgentRewards:
    rewards = _reward_preset_objective(max_steps=max_steps)

    w_heart = 0.02
    cap_heart = 0.2
    w_align_gear = 0.05
    cap_align_gear = 0.1
    w_scramble_gear = 0.05
    cap_scramble_gear = 0.1

    rewards.stats = {
        "heart.gained": w_heart,
        "aligner.gained": w_align_gear,
        "scrambler.gained": w_scramble_gear,
    }
    rewards.stats_max = {
        "heart.gained": cap_heart,
        "aligner.gained": cap_align_gear,
        "scrambler.gained": cap_scramble_gear,
    }

    w_deposit = 0.0005
    cap_deposit = 0.02
    for element in ["carbon", "oxygen", "germanium", "silicon"]:
        stat = f"collective.{element}.deposited"
        rewards.collective_stats[stat] = w_deposit
        rewards.collective_stats_max[stat] = cap_deposit

    return rewards


def _reward_preset_credit(*, max_steps: int) -> AgentRewards:
    rewards = _reward_preset_milestones(max_steps=max_steps)

    w_scramble_act = 0.2
    cap_scramble_act = 0.2
    w_align_act = 0.2
    cap_align_act = 0.2

    rewards.stats.update(
        {
            "junction.scrambled_by_agent": w_scramble_act,
            "junction.aligned_by_agent": w_align_act,
        }
    )
    rewards.stats_max.update(
        {
            "junction.scrambled_by_agent": cap_scramble_act,
            "junction.aligned_by_agent": cap_align_act,
        }
    )

    return rewards


def _apply_reward_preset(env: MettaGridConfig, *, reward_preset: RewardPreset) -> None:
    if reward_preset == "objective":
        return

    max_steps = env.game.max_steps
    if reward_preset == "milestones":
        env.game.agent.rewards = _reward_preset_milestones(max_steps=max_steps)
        return
    if reward_preset == "credit":
        env.game.agent.rewards = _reward_preset_credit(max_steps=max_steps)
        return
    raise ValueError(f"Unknown reward_preset: {reward_preset}")


def make_env(
    num_agents: int = 10,
    max_steps: int = 1000,
    reward_preset: RewardPreset = "objective",
) -> MettaGridConfig:
    """Create a CogsGuard environment."""
    env = make_cogsguard_mission(num_agents, max_steps).make_env()
    _apply_reward_preset(env, reward_preset=reward_preset)
    return env


def make_curriculum(
    env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
    reward_preset: RewardPreset = "objective",
) -> CurriculumConfig:
    env = env or make_env(reward_preset=reward_preset)

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
    reward_preset: RewardPreset = "objective",
) -> list[SimulationConfig]:
    env = env or make_env(reward_preset=reward_preset)

    return [
        SimulationConfig(suite="cogsguard", name="basic", env=env),
    ]


def train(
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    reward_preset: RewardPreset = "objective",
) -> TrainTool:
    return train_single_mission(
        curriculum=curriculum,
        policy_architecture=policy_architecture,
        teacher=teacher,
        reward_preset=reward_preset,
    )


def train_single_mission(
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    reward_preset: RewardPreset = "objective",
) -> TrainTool:
    from metta.agent.policies.vit import ViTDefaultConfig

    resolved_curriculum = curriculum or make_curriculum(reward_preset=reward_preset)
    trainer_cfg = TrainerConfig()
    training_env_cfg = TrainingEnvironmentConfig(curriculum=resolved_curriculum)
    evaluator_cfg = EvaluatorConfig(simulations=simulations(reward_preset=reward_preset))
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
    tt.policy_architecture = policy_architecture or ViTDefaultConfig()
    return tt


def evaluate(
    policy_uris: str | Sequence[str] | None = None,
    reward_preset: RewardPreset = "objective",
) -> EvaluateTool:
    resolved_policy_uris: str | list[str]
    if policy_uris is None:
        resolved_policy_uris = []
    elif isinstance(policy_uris, str):
        resolved_policy_uris = policy_uris
    else:
        resolved_policy_uris = list(policy_uris)
    return EvaluateTool(
        simulations=simulations(reward_preset=reward_preset),
        policy_uris=resolved_policy_uris,
    )


def play(policy_uri: Optional[str] = None) -> PlayTool:
    """Interactive play with a policy."""
    return PlayTool(sim=simulations()[0], policy_uri=policy_uri)


def replay(policy_uri: Optional[str] = None) -> ReplayTool:
    """Generate replay from a policy."""
    return ReplayTool(sim=simulations()[0], policy_uri=policy_uri)
