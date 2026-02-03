"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from typing import Literal, Optional, Sequence

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.mission import CvCMission
from cogames.cogs_vs_clips.reward_variants import apply_reward_variants
from cogames.cogs_vs_clips.sites import make_cogsguard_arena_site, make_cogsguard_machina1_site
from cogames.cogs_vs_clips.variants import NoClipsVariant
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
from metta.sweep.core import SweepParameters as SP
from metta.sweep.core import make_sweep
from mettagrid.config.mettagrid_config import MettaGridConfig

_CogsGuardLayout = Literal["machina_1", "arena"]


def _make_cogsguard_mission(*, layout: _CogsGuardLayout, num_agents: int, max_steps: int) -> CvCMission:
    if layout == "machina_1":
        site = make_cogsguard_machina1_site(num_agents)
        description = "Basic CogsGuard mission (Machina1 leaderboard layout)"
    elif layout == "arena":
        site = make_cogsguard_arena_site(num_agents)
        description = "Basic CogsGuard mission (arena layout)"
    else:
        raise ValueError(f"Unknown CogsGuard layout: {layout!r}")

    mission = CvCMission(
        name="basic",
        description=description,
        site=site,
        num_cogs=num_agents,
        max_steps=max_steps,
    )
    return mission.with_variants([NoClipsVariant()])


def make_env(
    num_agents: int = 8,
    max_steps: int = 10000,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
) -> MettaGridConfig:
    """Create a CogsGuard environment."""
    env = _make_cogsguard_mission(layout=layout, num_agents=num_agents, max_steps=max_steps).make_env()
    apply_reward_variants(env, variants=variants)
    return env


def make_curriculum(
    env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = "machina_1",
) -> CurriculumConfig:
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
    sweep_mode: bool = False,
) -> tools.TrainTool:
    if use_default_teacher:
        default_teacher = TeacherConfig(
            mode="supervisor",
            policy_uri="metta://policy/role?miner=4&aligner=2&scrambler=4",
            steps=5_500_000_000,
            teacher_led_proportion=0.0,
            anneal_start_step=2_500_000_000,
            ppo_begin_step=0,
        )
        if teacher is None:
            teacher = default_teacher
        else:
            teacher = default_teacher.model_copy(update=teacher.model_dump(exclude_unset=True), deep=True)
    from metta.agent.policies.vit import ViTDefaultConfig  # noqa: PLC0415

    resolved_curriculum = curriculum or make_curriculum(variants=variants, layout=layout)
    trainer_cfg = TrainerConfig()
    if sweep_mode:
        # Tuned from docs/experiments/cogsguard_sweep_2026-01-29.md.
        trainer_cfg.sampling.method = "prioritized"
        trainer_cfg.sampling.prio_alpha = 0.3098
        trainer_cfg.sampling.prio_beta0 = 0.7994
        trainer_cfg.advantage.gae_lambda = 0.9161
        trainer_cfg.advantage.gamma = 0.9995
        trainer_cfg.losses.ppo_actor.clip_coef = 0.3644
        trainer_cfg.losses.ppo_actor.ent_coef = 0.0717
        trainer_cfg.losses.ppo_critic.vf_coef = 1.3652
        trainer_cfg.optimizer.learning_rate = 0.00924
        trainer_cfg.optimizer.momentum = 0.9724
        trainer_cfg.optimizer.weight_decay = 0.10
        trainer_cfg.optimizer.eps = 2.5e-06
        trainer_cfg.optimizer.warmup_steps = 1752
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
    default_architecture = ViTDefaultConfig(obs_shim_ignore_inventory_power_tokens=False)
    if sweep_mode:
        default_architecture = ViTDefaultConfig(
            obs_shim_ignore_inventory_power_tokens=False,
            actor_hidden=384,
            critic_hidden=768,
            latent_dim=96,
            core_resnet_layers=1,
            core_num_heads=4,
            core_num_latents=16,
        )
    tt.policy_architecture = policy_architecture or default_architecture
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


def train_sweep(
    variants: Optional[Sequence[str]] = ("milestones", "credit"),
    layout: _CogsGuardLayout = "machina_1",
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    use_default_teacher: bool = False,
) -> tools.TrainTool:
    tool = train(
        policy_architecture=policy_architecture,
        teacher=teacher,
        variants=variants,
        layout=layout,
        use_default_teacher=use_default_teacher,
        sweep_mode=True,
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
    # Basic sweep search space (simplified from cogs_v_clips)
    search_space: dict[str, object] = {}
    if sweep_reward_variants:
        search_space.update(
            SP.categorical(
                "variants",
                choices=[
                    "[]",
                    '["milestones"]',
                    '["credit"]',
                    '["milestones","credit"]',
                ],
            )
        )
    elif variants is not None:
        search_space["variants"] = list(variants)

    return make_sweep(
        name=sweep_name,
        recipe="recipes.experiment.cogsguard",
        train_entrypoint="train_sweep",
        eval_entrypoint="evaluate_stub",
        metric_key="env_collective/cogs/aligned.junction.held",
        search_space=search_space,
        cost_key="metric/total_time",
        max_trials=max_trials,
        num_parallel_trials=num_parallel_trials,
    )
