"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Sequence

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.cogsguard_curriculum import (
    COGSGUARD_FIXED_MAPS,
    EventProfile,
    filter_compatible_variants,
    resolve_event_profiles,
    split_variants,
)
from cogames.cogs_vs_clips.evals.cogsguard_evals import COGSGUARD_EVAL_COGS, COGSGUARD_EVAL_MISSIONS
from cogames.cogs_vs_clips.mission import CvCMission
from cogames.cogs_vs_clips.reward_variants import apply_reward_variants
from cogames.cogs_vs_clips.sites import MAPS_DIR, make_cogsguard_arena_site, make_cogsguard_machina1_site
from cogames.core import CoGameMissionVariant, CoGameSite
from metta.agent.policies.vit import ViTDefaultConfig
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import (
    CurriculumAlgorithmConfig,
    CurriculumConfig,
    DiscreteRandomConfig,
)
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.rl.training.clips_curriculum import ClipsCurriculumConfig
from metta.rl.training.scheduler import LossRunGate, SchedulerConfig, ScheduleRule
from metta.rl.training.teacher import TeacherConfig, apply_teacher_phase
from metta.sim.simulation_config import SimulationConfig
from metta.sweep.core import SweepParameters as SP
from metta.sweep.core import make_sweep
from mettagrid.config.mettagrid_config import MettaGridConfig
from mettagrid.map_builder.map_builder import MapBuilderConfig
from mettagrid.mapgen.mapgen import MapGen, MapGenConfig

_CogsGuardLayout = Literal["machina_1", "arena"]
DEFAULT_LAYOUT: _CogsGuardLayout = "machina_1"
DEFAULT_NUM_AGENTS = 8
DEFAULT_MAX_STEPS = 10000
DEFAULT_INCLUDE_EVAL_MISSIONS = False
DEFAULT_INCLUDE_FIXED_MAPS = False


def _make_cogsguard_mission(
    *,
    layout: _CogsGuardLayout,
    num_agents: int,
    max_steps: int,
    variants: Sequence[CoGameMissionVariant] | None = None,
    clips_overrides: dict[str, object] | None = None,
    weather_overrides: dict[str, object] | None = None,
) -> CvCMission:
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
    if clips_overrides:
        mission.clips = mission.clips.model_copy(update=clips_overrides)
    if weather_overrides:
        mission.weather = mission.weather.model_copy(update=weather_overrides)
    if variants:
        compatible = filter_compatible_variants(mission, variants)
        if compatible:
            mission = mission.with_variants(compatible)
    return mission


def _make_env_from_variants(
    *,
    num_agents: int,
    max_steps: int,
    variants: Sequence[CoGameMissionVariant] | None,
    reward_variants: Sequence[str] | None,
    event_profile_name: str | None,
    clips_overrides: dict[str, object] | None,
    weather_overrides: dict[str, object] | None,
    layout: _CogsGuardLayout,
) -> MettaGridConfig:
    env = _make_cogsguard_mission(
        layout=layout,
        num_agents=num_agents,
        max_steps=max_steps,
        variants=variants,
        clips_overrides=clips_overrides,
        weather_overrides=weather_overrides,
    ).make_env()
    if reward_variants:
        apply_reward_variants(env, variants=list(reward_variants))
    if event_profile_name:
        env.label = f"{env.label}.{event_profile_name}"
    return env


def _make_eval_envs(
    *,
    num_agents: int,
    max_steps: int,
    variants: Sequence[CoGameMissionVariant],
    reward_variants: Sequence[str] | None,
    event_profile_name: str | None,
    clips_overrides: dict[str, object] | None,
    weather_overrides: dict[str, object] | None,
) -> list[MettaGridConfig]:
    eval_envs: list[MettaGridConfig] = []
    for mission in COGSGUARD_EVAL_MISSIONS:
        map_key = f"evals/{mission.name}.map"
        spawn_count = COGSGUARD_EVAL_COGS.get(map_key)
        if spawn_count is not None and spawn_count < num_agents:
            continue
        site = mission.site.model_copy(update={"min_cogs": num_agents, "max_cogs": num_agents})
        eval_mission = CvCMission(
            name=mission.name,
            description=mission.description,
            site=site,
            num_cogs=num_agents,
            max_steps=max_steps,
        )
        if clips_overrides:
            eval_mission.clips = eval_mission.clips.model_copy(update=clips_overrides)
        if weather_overrides:
            eval_mission.weather = eval_mission.weather.model_copy(update=weather_overrides)
        if variants:
            compatible = filter_compatible_variants(eval_mission, variants)
            if compatible:
                eval_mission = eval_mission.with_variants(compatible)
        env = eval_mission.make_env()
        if reward_variants:
            apply_reward_variants(env, variants=list(reward_variants))
        if event_profile_name:
            env.label = f"{env.label}.{event_profile_name}"
        eval_envs.append(env)
    return eval_envs


def _count_spawn_pads(map_path: Path) -> int:
    text = map_path.read_text()
    if "map_data:" not in text:
        raise ValueError(f"Missing map_data block in {map_path}")
    map_section = text.split("map_data:", 1)[1].split("char_to_map_name:", 1)[0]
    count = map_section.count("@")
    if count <= 0:
        raise ValueError(f"No spawn pads found in {map_path}")
    return count


def _load_ascii_map(map_name: str) -> MapGenConfig:
    map_path = MAPS_DIR / map_name
    if not map_path.exists():
        raise FileNotFoundError(f"Map not found: {map_path}")
    return MapGen.Config(
        instance=MapBuilderConfig.from_uri(str(map_path)),
        instances=1,
        fixed_spawn_order=False,
        instance_border_width=0,
    )


def _make_fixed_map_envs(
    *,
    num_agents: int,
    max_steps: int,
    variants: Sequence[CoGameMissionVariant],
    reward_variants: Sequence[str] | None,
    event_profile_name: str | None,
    clips_overrides: dict[str, object] | None,
    weather_overrides: dict[str, object] | None,
) -> list[MettaGridConfig]:
    envs: list[MettaGridConfig] = []
    for map_name in COGSGUARD_FIXED_MAPS:
        map_path = MAPS_DIR / map_name
        if not map_path.exists():
            raise FileNotFoundError(f"Map not found: {map_path}")
        spawn_count = _count_spawn_pads(map_path)
        if spawn_count < num_agents:
            continue

        stem = Path(map_name).stem
        site = CoGameSite(
            name=f"cogsguard_fixed_{stem}",
            description=f"CogsGuard fixed map: {stem}",
            map_builder=_load_ascii_map(map_name),
            min_cogs=num_agents,
            max_cogs=num_agents,
        )
        mission = CvCMission(
            name="fixed",
            description=f"CogsGuard fixed map: {stem}",
            site=site,
            num_cogs=num_agents,
            max_steps=max_steps,
        )
        if clips_overrides:
            mission.clips = mission.clips.model_copy(update=clips_overrides)
        if weather_overrides:
            mission.weather = mission.weather.model_copy(update=weather_overrides)
        if variants:
            compatible = filter_compatible_variants(mission, variants)
            if compatible:
                mission = mission.with_variants(compatible)
        env = mission.make_env()
        if reward_variants:
            apply_reward_variants(env, variants=list(reward_variants))
        if event_profile_name:
            env.label = f"{env.label}.{event_profile_name}"
        envs.append(env)
    return envs


def _resolve_max_steps_buckets(max_steps: int, max_steps_buckets: Sequence[int] | None) -> list[int]:
    if max_steps_buckets is None:
        buckets = [max_steps]
    else:
        buckets = list(max_steps_buckets)
    buckets = sorted(set(int(steps) for steps in buckets if 0 < steps <= max_steps))
    if max_steps not in buckets:
        buckets.append(max_steps)
    buckets = sorted(set(buckets))
    return buckets


def _supports_seed_bucket(env: MettaGridConfig) -> bool:
    return isinstance(env.game.map_builder, MapGen.Config)


def make_env(
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
) -> MettaGridConfig:
    """Create a CogsGuard environment."""
    resolved_variants, resolved_rewards = split_variants(variants)
    return _make_env_from_variants(
        num_agents=num_agents,
        max_steps=max_steps,
        variants=resolved_variants,
        reward_variants=resolved_rewards,
        event_profile_name=None,
        clips_overrides=None,
        weather_overrides=None,
        layout=layout,
    )


def make_curriculum(
    env: Optional[MettaGridConfig] = None,
    algorithm_config: Optional[CurriculumAlgorithmConfig] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
) -> CurriculumConfig:
    if algorithm_config is None:
        algorithm_config = DiscreteRandomConfig()

    if env is not None:
        if _supports_seed_bucket(env):
            task_generators = [cc.bucketed(env)]
        else:
            task_generators = [cc.single_task(env)]
    else:
        resolved_variants, resolved_rewards = split_variants(variants)
        resolved_event_profiles = resolve_event_profiles(event_profiles)
        label_event_profiles = event_profiles is not None
        resolved_max_steps = _resolve_max_steps_buckets(max_steps, max_steps_buckets)
        task_generators = []
        for bucket_steps in resolved_max_steps:
            for event_profile in resolved_event_profiles:
                event_name = event_profile.name if label_event_profiles else None
                task_generators.append(
                    cc.bucketed(
                        _make_env_from_variants(
                            num_agents=num_agents,
                            max_steps=bucket_steps,
                            variants=resolved_variants,
                            reward_variants=resolved_rewards,
                            event_profile_name=event_name,
                            clips_overrides=event_profile.clips_overrides,
                            weather_overrides=event_profile.weather_overrides,
                            layout=layout,
                        )
                    )
                )
            if include_eval_missions:
                for event_profile in resolved_event_profiles:
                    event_name = event_profile.name if label_event_profiles else None
                    task_generators.extend(
                        cc.bucketed(env_cfg)
                        for env_cfg in _make_eval_envs(
                            num_agents=num_agents,
                            max_steps=bucket_steps,
                            variants=resolved_variants,
                            reward_variants=resolved_rewards,
                            event_profile_name=event_name,
                            clips_overrides=event_profile.clips_overrides,
                            weather_overrides=event_profile.weather_overrides,
                        )
                    )
            if include_fixed_maps:
                for event_profile in resolved_event_profiles:
                    event_name = event_profile.name if label_event_profiles else None
                    task_generators.extend(
                        cc.bucketed(env_cfg)
                        for env_cfg in _make_fixed_map_envs(
                            num_agents=num_agents,
                            max_steps=bucket_steps,
                            variants=resolved_variants,
                            reward_variants=resolved_rewards,
                            event_profile_name=event_name,
                            clips_overrides=event_profile.clips_overrides,
                            weather_overrides=event_profile.weather_overrides,
                        )
                    )

    if seed_span is None:
        seed_span = cc.Span(0, 1_000_000)

    for task_gen in task_generators:
        child = task_gen.child_generator_config
        if isinstance(child, cc.SingleTaskGenerator.Config) and _supports_seed_bucket(child.env):
            task_gen.add_bucket("game.map_builder.seed", [seed_span])

    if len(task_generators) == 1:
        tasks = task_generators[0]
    else:
        tasks = cc.merge(task_generators)

    return tasks.to_curriculum(algorithm_config=algorithm_config)


def simulations(
    env: Optional[MettaGridConfig] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
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
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
    sweep_mode: bool = False,
    use_clips_curriculum: bool = False,
) -> tools.TrainTool:
    if teacher is None:
        teacher = TeacherConfig()
    elif isinstance(teacher, dict):
        teacher = TeacherConfig.model_validate(teacher)

    if use_clips_curriculum:
        default_clips = ClipsCurriculumConfig(layout=layout)
        if curriculum is None:
            curriculum = default_clips
        else:
            overrides = curriculum if isinstance(curriculum, dict) else curriculum.model_dump(exclude_unset=True)
            curriculum = default_clips.model_copy(update=overrides, deep=True)
        resolved_curriculum = curriculum
    else:
        resolved_curriculum = curriculum or make_curriculum(
            variants=variants,
            layout=layout,
            num_agents=num_agents,
            max_steps=max_steps,
            include_eval_missions=include_eval_missions,
            include_fixed_maps=include_fixed_maps,
            max_steps_buckets=max_steps_buckets,
            seed_span=seed_span,
            event_profiles=event_profiles,
        )
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
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
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
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
) -> tools.PlayTool:
    """Interactive play with a policy."""
    return tools.PlayTool(sim=simulations(variants=variants, layout=layout)[0], policy_uri=policy_uri)


def replay(
    policy_uri: Optional[str] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
) -> tools.ReplayTool:
    """Generate replay from a policy."""
    return tools.ReplayTool(sim=simulations(variants=variants, layout=layout)[0], policy_uri=policy_uri)


def train_sweep(
    variants: Optional[Sequence[str]] = ("milestones", "credit"),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
) -> tools.TrainTool:
    tool = train(
        policy_architecture=policy_architecture,
        teacher=teacher,
        variants=variants,
        layout=layout,
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
