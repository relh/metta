"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from typing import Literal, Optional, Sequence

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.cogsguard_reward_variants import apply_reward_variants
from cogames.cogs_vs_clips.mission import Mission
from cogames.cogs_vs_clips.sites import make_cogsguard_arena_site, make_cogsguard_machina1_site
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
from mettagrid.config.mettagrid_config import MettaGridConfig

_CogsGuardLayout = Literal["machina_1", "arena"]


def _normalize_variants(variants: str | Sequence[str] | None) -> list[str]:
    """Normalize reward variants to a list of variant names.

    Note: an empty list means "no variants" (use mission defaults).
    """
    if variants is None:
        return []
    if isinstance(variants, str):
        return [variants]
    return list(variants)


def _make_cogsguard_mission(*, layout: _CogsGuardLayout, num_agents: int, max_steps: int) -> Mission:
    if layout == "machina_1":
        site = make_cogsguard_machina1_site(num_agents)
        description = "Basic CogsGuard mission (Machina1 layout)"
    elif layout == "arena":
        site = make_cogsguard_arena_site(num_agents)
        description = "Basic CogsGuard mission (arena layout)"
    else:
        raise ValueError(f"Unknown CogsGuard layout: {layout!r}")

    return Mission(
        name="basic",
        description=description,
        site=site,
        num_cogs=num_agents,
        max_steps=max_steps,
    )


def make_env(
    num_agents: int = 10,
    max_steps: int = 10000,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
) -> MettaGridConfig:
    """Create a CogsGuard environment."""
    variants = _normalize_variants(variants)
    env = _make_cogsguard_mission(layout=layout, num_agents=num_agents, max_steps=max_steps).make_env()
    apply_reward_variants(env, variants=variants)
    return env


def make_curriculum(
    env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
) -> CurriculumConfig:
    # Reward variants are stackable, so we keep a single env/curriculum and pass
    # the full variant list through.
    env = env or make_env(variants=variants, layout=layout)
    tasks = cc.single_task(env)

    if algorithm_config is None:
        algorithm_config = DiscreteRandomConfig()

    return tasks.to_curriculum(algorithm_config=algorithm_config)


def simulations(
    env: Optional[MettaGridConfig] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
) -> list[SimulationConfig]:
    env = env or make_env(variants=variants, layout=layout)

    return [
        SimulationConfig(suite="cogsguard", name=f"basic_{layout}", env=env),
    ]


def train(
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
    use_default_teacher: bool = False,
) -> tools.TrainTool:
    if teacher is None and use_default_teacher:
        teacher = TeacherConfig(
            mode="supervisor",
            policy_uri="metta://policy/pinky?miner=4&aligner=2&scrambler=4",
            steps=5_500_000_000,
            teacher_led_proportion=0.0,
            anneal_start_step=2_500_000_000,
            ppo_begin_step=0,
        )
    from metta.agent.policies.vit import ViTDefaultConfig

    resolved_curriculum = curriculum or make_curriculum(variants=variants, layout=layout)
    trainer_cfg = TrainerConfig()
    training_env_cfg = TrainingEnvironmentConfig(curriculum=resolved_curriculum)
    evaluator_cfg = EvaluatorConfig(simulations=simulations(variants=variants, layout=layout))
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

    tt = tools.TrainTool(
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
    layout: _CogsGuardLayout = "machina_1",
) -> tools.EvaluateTool:
    resolved_policy_uris: str | list[str]
    if policy_uris is None:
        resolved_policy_uris = []
    elif isinstance(policy_uris, str):
        resolved_policy_uris = policy_uris
    else:
        resolved_policy_uris = list(policy_uris)
    return tools.EvaluateTool(
        simulations=simulations(variants=variants, layout=layout),
        policy_uris=resolved_policy_uris,
    )


def play(
    policy_uri: Optional[str] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
) -> tools.PlayTool:
    """Interactive play with a policy."""
    return tools.PlayTool(sim=simulations(variants=variants, layout=layout)[0], policy_uri=policy_uri)


def replay(
    policy_uri: Optional[str] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
) -> tools.ReplayTool:
    """Generate replay from a policy."""
    return tools.ReplayTool(sim=simulations(variants=variants, layout=layout)[0], policy_uri=policy_uri)
