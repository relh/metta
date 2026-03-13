"""A Cogs vs Clips version of the arena recipe - STABLE

This is meant as a basic testbed for CvC buildings / mechanics.
This recipe is automatically validated in CI and release processes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Sequence

import torch
from cortex import RoutedAdapterConfig
from cortex.rl.feature_extractors import BoxCNNFeatureExtractorConfig

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.core import CoGameMissionVariant
from cogames.games.cogs_vs_clips.evals.cvc_evals import (
    CVC_EVAL_COGS,
    CVC_EVAL_MISSIONS,
)
from cogames.games.cogs_vs_clips.evals.diagnostic_evals import MAPS_DIR
from cogames.games.cogs_vs_clips.game import ClipsVariant
from cogames.games.cogs_vs_clips.game.clips import ClipsConfig
from cogames.games.cogs_vs_clips.game.damage import DamageVariant
from cogames.games.cogs_vs_clips.game.days import DayConfig, DaysVariant
from cogames.games.cogs_vs_clips.missions.arena import make_arena_map_builder
from cogames.games.cogs_vs_clips.missions.machina_1 import make_machina1_map_builder
from cogames.games.cogs_vs_clips.missions.mission import CvCMission
from cogames.games.cogs_vs_clips.train.cvc_curriculum import (
    CVC_FIXED_MAPS,
    EventProfile,
    filter_compatible_variants,
    normalize_variant_names,
    resolve_event_profiles,
    split_variants,
)
from cogames.games.cogs_vs_clips.train.reward_variants import (
    AVAILABLE_REWARD_VARIANTS,
    apply_reward_variants,
)
from metta.agent.policies.default import DefaultPolicyConfig
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import (
    CurriculumAlgorithmConfig,
    CurriculumConfig,
    DiscreteRandomConfig,
)
from metta.rl.diff_horde.cumulants import DiffHordeCumulantsConfig
from metta.rl.diff_horde.presets.cogsguard import resolve_cogsguard_horde_cumulants
from metta.rl.loss.diff_horde import DiffHordeLossConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig
from metta.rl.training.clips_curriculum import ClipsCurriculumConfig
from metta.rl.training.scheduler import LossRunGate, SchedulerConfig, ScheduleRule
from metta.rl.training.teacher import TeacherConfig, apply_teacher_phase
from metta.sim.simulation_config import SimulationConfig
from metta.sweep.core import Distribution as D
from metta.sweep.core import SweepParameters as SP
from metta.sweep.core import make_sweep
from mettagrid.config.mettagrid_config import MettaGridConfig
from mettagrid.map_builder.map_builder import MapBuilderConfig
from mettagrid.mapgen.mapgen import MapGen, MapGenConfig
from mettagrid.policy.policy_env_interface import PolicyEnvInterface

_CogsGuardLayout = Literal["machina_1", "arena"]
DEFAULT_LAYOUT: _CogsGuardLayout = "machina_1"
DEFAULT_NUM_AGENTS = 8
DEFAULT_MAX_STEPS = 10000
DEFAULT_INCLUDE_EVAL_MISSIONS = False
DEFAULT_INCLUDE_FIXED_MAPS = False


# Tuned from relh.cg.adapters.0213.2_trial_0017_315178 (best full-length AUC).
_TUNED_PARAMS = {
    # Routed Adapter
    "routed_adapter.rank": 8,
    "routed_adapter.trunk_lr_mult": 0.5476294593341358,
    # Trainer Config
    "trainer.sampling.method": "sequential",
    "trainer.sampling.prio_alpha": 0.0,
    "trainer.sampling.prio_beta0": 0.6,
    "trainer.advantage.gae_lambda": 0.9354159832000732,
    "trainer.advantage.gamma": 0.9986186027526855,
    "trainer.optimizer.learning_rate": 0.00737503357231617,
    "trainer.optimizer.momentum": 0.9794994592666626,
    "trainer.optimizer.weight_decay": 0.3,
    "trainer.optimizer.eps": 6.686864253424574e-06,
    "trainer.optimizer.warmup_steps": 500,
    "trainer.losses.ppo_actor.clip_coef": 0.36670681834220886,
    "trainer.losses.ppo_actor.ent_coef": 0.02566424384713173,
    "trainer.losses.ppo_critic.vf_coef": 1.4647305011749268,
}


def _overrides_disable_change_vibe(overrides: object) -> bool:
    if not isinstance(overrides, dict):
        return False
    if "game.actions.change_vibe.enabled" not in overrides:
        return False
    return overrides["game.actions.change_vibe.enabled"] is False


def _vibe_actions_enabled(*, training_env_cfg: TrainingEnvironmentConfig) -> bool:
    task_gen = training_env_cfg.curriculum.task_generator
    if _overrides_disable_change_vibe(getattr(task_gen, "overrides", None)):
        return False
    child_gen = getattr(task_gen, "child_generator_config", None)
    return not _overrides_disable_change_vibe(getattr(child_gen, "overrides", None))


def _wire_vibe_actor_loss(*, trainer_cfg: TrainerConfig, slice_configs: Sequence[object]) -> None:
    if not trainer_cfg.losses.has_loss("ppo_vibe_actor"):
        base_actor_cfg = trainer_cfg.losses["ppo_actor"]
        base_loss_coef = float(getattr(base_actor_cfg, "loss_coef", 1.0))
        split_loss_coef = base_loss_coef / 2.0
        if hasattr(base_actor_cfg, "loss_coef"):
            base_actor_cfg.loss_coef = split_loss_coef
        trainer_cfg.losses.add_loss(
            "ppo_vibe_actor",
            PPOActorConfig(
                actor_name="vibe",
                log_prob_key="vibe_act_log_prob",
                entropy_key="vibe_entropy",
                loss_coef=split_loss_coef,
                replay_ratio_key="vibe_ratio",
                extra_action_keys=["vibe_actions"],
            ),
        )

    for slice_cfg in slice_configs:
        losses = getattr(slice_cfg, "losses", None)
        if not isinstance(losses, list):
            continue
        if "ppo_actor" not in losses or "ppo_vibe_actor" in losses:
            continue
        insert_at = losses.index("ppo_actor") + 1
        losses.insert(insert_at, "ppo_vibe_actor")


def _sync_slice_advantage(*, trainer_cfg: TrainerConfig, slice_configs: Sequence[object]) -> None:
    for slice_cfg in slice_configs:
        slice_cfg.advantage = trainer_cfg.advantage


def _with_horde_num_cumulants(policy_architecture: PolicyArchitecture, num_cumulants: int) -> PolicyArchitecture:
    if not hasattr(policy_architecture, "horde_num_cumulants"):
        raise ValueError(
            "diff_horde_cumulants requires a policy architecture with 'horde_num_cumulants' "
            f"(got {type(policy_architecture).__name__})"
        )
    return policy_architecture.model_copy(update={"horde_num_cumulants": num_cumulants})


def _infer_td_key_cumulant_sizes_from_policy(
    *,
    cumulants: DiffHordeCumulantsConfig,
    policy_architecture: PolicyArchitecture,
    curriculum: CurriculumConfig,
) -> None:
    if not any(spec.kind == "td_key" and spec.size is None for spec in cumulants.specs):
        return
    env_cfg = cc.Curriculum(curriculum).get_task().get_env_cfg()
    policy_env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)
    policy = policy_architecture.model_copy(deep=True).make_policy(policy_env_info)
    policy.initialize_to_environment(policy_env_info, torch.device("cpu"))
    cumulants.infer_td_key_sizes_from_policy(policy)


def _merge_cumulants_by_name(
    *,
    base: DiffHordeCumulantsConfig,
    override: DiffHordeCumulantsConfig,
) -> DiffHordeCumulantsConfig:
    merged_specs: dict[str, dict[str, object]] = {spec.name: spec.model_dump(exclude_none=True) for spec in base.specs}
    for spec in override.specs:
        merged_specs[spec.name] = spec.model_dump(exclude_none=True)
    return DiffHordeCumulantsConfig.model_validate(merged_specs)


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
        map_builder = make_machina1_map_builder(num_agents)
        description = "Basic CogsGuard mission (Machina1 leaderboard layout)"
    elif layout == "arena":
        map_builder = make_arena_map_builder(num_agents)
        description = "Basic CogsGuard mission (arena layout)"
    else:
        raise ValueError(f"Unknown CogsGuard layout: {layout!r}")

    mission = CvCMission(
        name=f"cogsguard_{layout}.basic",
        description=description,
        map_builder=map_builder,
        num_agents=num_agents,
        num_cogs=num_agents,
        min_cogs=num_agents,
        max_cogs=num_agents,
        max_steps=max_steps,
    )
    base_variants: list[CoGameMissionVariant] = [
        DamageVariant(),
        DaysVariant(days_config=DayConfig(**(weather_overrides or {}))),
    ]
    if not (clips_overrides and clips_overrides.get("disabled") is True):
        base_variants.append(ClipsVariant(clips_config=ClipsConfig(**(clips_overrides or {}))))
    mission = mission.with_variants(base_variants)
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
    for mission in CVC_EVAL_MISSIONS:
        map_key = f"evals/{mission.name}.map"
        spawn_count = CVC_EVAL_COGS.get(map_key)
        if spawn_count is not None and spawn_count < num_agents:
            continue
        eval_mission = CvCMission(
            name=mission.name,
            description=mission.description,
            map_builder=mission.map_builder,
            num_agents=num_agents,
            num_cogs=num_agents,
            min_cogs=num_agents,
            max_cogs=num_agents,
            max_steps=max_steps,
        )
        eval_base_variants: list[CoGameMissionVariant] = [
            DamageVariant(),
            DaysVariant(days_config=DayConfig(**(weather_overrides or {}))),
        ]
        if not (clips_overrides and clips_overrides.get("disabled") is True):
            eval_base_variants.append(ClipsVariant(clips_config=ClipsConfig(**(clips_overrides or {}))))
        eval_mission = eval_mission.with_variants(eval_base_variants)
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
    for map_name in CVC_FIXED_MAPS:
        map_path = MAPS_DIR / map_name
        if not map_path.exists():
            raise FileNotFoundError(f"Map not found: {map_path}")
        spawn_count = _count_spawn_pads(map_path)
        if spawn_count < num_agents:
            continue

        stem = Path(map_name).stem
        mission = CvCMission(
            name=f"cogsguard_fixed_{stem}",
            description=f"CogsGuard fixed map: {stem}",
            map_builder=_load_ascii_map(map_name),
            num_agents=num_agents,
            num_cogs=num_agents,
            min_cogs=num_agents,
            max_cogs=num_agents,
            max_steps=max_steps,
        )
        fixed_base_variants: list[CoGameMissionVariant] = [
            DamageVariant(),
            DaysVariant(days_config=DayConfig(**(weather_overrides or {}))),
        ]
        if not (clips_overrides and clips_overrides.get("disabled") is True):
            fixed_base_variants.append(ClipsVariant(clips_config=ClipsConfig(**(clips_overrides or {}))))
        mission = mission.with_variants(fixed_base_variants)
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
    buckets = [max_steps] if max_steps_buckets is None else list(max_steps_buckets)
    buckets = sorted(set(int(steps) for steps in buckets if 0 < steps <= max_steps))
    if max_steps not in buckets:
        buckets.append(max_steps)
    return sorted(set(buckets))


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
        task_generators = [cc.bucketed(env)] if _supports_seed_bucket(env) else [cc.single_task(env)]
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

    tasks = task_generators[0] if len(task_generators) == 1 else cc.merge(task_generators)

    return tasks.to_curriculum(algorithm_config=algorithm_config)


def simulations(
    env: Optional[MettaGridConfig] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> list[SimulationConfig]:
    env = env or make_env(variants=variants, layout=layout, num_agents=num_agents, max_steps=max_steps)

    return [
        SimulationConfig(suite="cogsguard", name=f"basic_{layout}", env=env),
    ]


def train(
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: PolicyArchitecture | str | None = None,
    teacher: Optional[TeacherConfig] = None,
    diff_horde_cumulants: DiffHordeCumulantsConfig | dict[str, object] | list[dict[str, object]] | None = None,
    horde_variants: str | Sequence[str] | None = None,
    diff_horde_gamma: float | Sequence[float] | None = None,
    diff_horde_lambda: float | Sequence[float] | None = None,
    diff_horde_normalize_cumulants: bool | None = None,
    diff_horde_cumulant_centering: Literal["none", "ema"] | None = None,
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
    routed_adapter: RoutedAdapterConfig | None = None,
) -> tools.TrainTool:
    if isinstance(policy_architecture, str):
        policy_architecture = PolicyArchitecture.from_spec(policy_architecture)

    if sweep_mode and routed_adapter is None and policy_architecture is None:
        # Tuned from relh.cg.adapters.0213.2_trial_0017_315178 (best full-length AUC).
        routed_adapter = RoutedAdapterConfig(
            rank=8,
            trunk_lr_mult=0.5476294593341358,
            num_slots=num_agents,
        )

    if routed_adapter is not None and not routed_adapter.enabled:
        routed_adapter = None

    if use_clips_curriculum:
        default_clips = ClipsCurriculumConfig(layout=layout)
        if curriculum is None:
            curriculum = default_clips
        else:
            overrides = curriculum.model_dump(exclude_unset=True)
            curriculum = default_clips.model_copy(update=overrides, deep=True)
    else:
        curriculum = curriculum or make_curriculum(
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
    # Tuned from relh.cg.adapters.0213.2_trial_0017_315178 (best full-length AUC).
    trainer_cfg.sampling.method = "sequential"
    trainer_cfg.sampling.prio_alpha = 0.0
    trainer_cfg.sampling.prio_beta0 = 0.6
    trainer_cfg.advantage.gae_lambda = 0.9354159832000732
    trainer_cfg.advantage.gamma = 0.9986186027526855
    trainer_cfg.optimizer.learning_rate = 0.00737503357231617
    trainer_cfg.optimizer.momentum = 0.9794994592666626
    trainer_cfg.optimizer.weight_decay = 0.3
    trainer_cfg.optimizer.eps = 6.686864253424574e-06
    trainer_cfg.optimizer.warmup_steps = 500
    trainer_cfg.losses.ppo_actor.clip_coef = 0.36670681834220886
    trainer_cfg.losses.ppo_actor.ent_coef = 0.02566424384713173
    trainer_cfg.losses.ppo_critic.vf_coef = 1.4647305011749268
    training_env_cfg = TrainingEnvironmentConfig(curriculum=curriculum)
    evaluator_cfg = EvaluatorConfig(simulations=simulations(variants=variants, layout=layout))

    default_architecture = DefaultPolicyConfig(
        actor_hidden=128,
        critic_hidden=256,
        feature_extractor=BoxCNNFeatureExtractorConfig(
            output_dim=64,
        ),
        cortex_routed_adapter=routed_adapter,
    )
    if sweep_mode:
        default_architecture = DefaultPolicyConfig(
            actor_hidden=384,
            critic_hidden=768,
            cortex_num_layers=1,
            feature_extractor=BoxCNNFeatureExtractorConfig(
                output_dim=96,
            ),
            cortex_routed_adapter=routed_adapter,
        )

    resolved_architecture = policy_architecture
    if resolved_architecture is None:
        resolved_architecture = default_architecture
    elif routed_adapter is not None and isinstance(resolved_architecture, DefaultPolicyConfig):
        if resolved_architecture.cortex_routed_adapter is not None:
            raise ValueError(
                "routed_adapter was provided, but policy_architecture already sets cortex_routed_adapter. "
                "Remove one of them."
            )
        resolved_architecture = resolved_architecture.model_copy(update={"cortex_routed_adapter": routed_adapter})
    elif routed_adapter is not None:
        raise ValueError(
            "routed_adapter only supports the default Cortex policy architecture. "
            "Pass a DefaultPolicyConfig(cortex_routed_adapter=...) explicitly to use a custom architecture."
        )

    resolved_diff_horde_cumulants = resolve_cogsguard_horde_cumulants(horde_variants)
    if diff_horde_cumulants is not None:
        if isinstance(diff_horde_cumulants, DiffHordeCumulantsConfig):
            explicit_cumulants = diff_horde_cumulants
        else:
            explicit_cumulants = DiffHordeCumulantsConfig.model_validate(diff_horde_cumulants)
        if resolved_diff_horde_cumulants is None:
            resolved_diff_horde_cumulants = explicit_cumulants
        else:
            resolved_diff_horde_cumulants = _merge_cumulants_by_name(
                base=resolved_diff_horde_cumulants,
                override=explicit_cumulants,
            )

    if resolved_diff_horde_cumulants is not None:
        _infer_td_key_cumulant_sizes_from_policy(
            cumulants=resolved_diff_horde_cumulants,
            policy_architecture=resolved_architecture,
            curriculum=curriculum,
        )
        resolved_architecture = _with_horde_num_cumulants(
            policy_architecture=resolved_architecture,
            num_cumulants=resolved_diff_horde_cumulants.num_cumulants,
        )

    policy_assets = {"learner0": PolicyAssetConfig(architecture=resolved_architecture)}

    tt = tools.TrainTool(
        trainer=trainer_cfg,
        training_env=training_env_cfg,
        evaluator=evaluator_cfg,
        policy_assets=policy_assets,
    )
    if _vibe_actions_enabled(training_env_cfg=training_env_cfg):
        _wire_vibe_actor_loss(trainer_cfg=trainer_cfg, slice_configs=tt.trajectory_isolation.slices)
    # Determinism is useful for debugging, but it can significantly reduce CUDA throughput.
    # Users can re-enable it via `system.torch_deterministic=true` when needed.
    tt.system.torch_deterministic = False

    if teacher and teacher.enabled:
        scheduler_run_gates: list[LossRunGate] = []
        scheduler_rules: list[ScheduleRule] = []
        apply_teacher_phase(
            trainer_cfg=trainer_cfg,
            losses=trainer_cfg.losses,
            training_env_cfg=training_env_cfg,
            policy_assets=tt.policy_assets,
            scheduler_rules=scheduler_rules,
            scheduler_run_gates=scheduler_run_gates,
            teacher_cfg=teacher,
            trajectory_isolation=tt.trajectory_isolation,
        )
        if _vibe_actions_enabled(training_env_cfg=training_env_cfg):
            _wire_vibe_actor_loss(trainer_cfg=trainer_cfg, slice_configs=tt.trajectory_isolation.slices)
        tt.scheduler = SchedulerConfig(run_gates=scheduler_run_gates, rules=scheduler_rules)

    _sync_slice_advantage(trainer_cfg=trainer_cfg, slice_configs=tt.trajectory_isolation.slices)

    if resolved_diff_horde_cumulants is not None:
        diff_horde_loss_cfg = DiffHordeLossConfig(cumulants=resolved_diff_horde_cumulants)
        diff_horde_updates: dict[str, object] = {}
        if diff_horde_gamma is not None:
            diff_horde_updates["gamma"] = diff_horde_gamma
        if diff_horde_lambda is not None:
            diff_horde_updates["lambda_"] = diff_horde_lambda
        if diff_horde_normalize_cumulants is not None:
            diff_horde_updates["normalize_cumulants"] = diff_horde_normalize_cumulants
        if diff_horde_cumulant_centering is not None:
            diff_horde_updates["cumulant_centering"] = diff_horde_cumulant_centering
        if diff_horde_updates:
            payload = diff_horde_loss_cfg.model_dump(mode="python")
            payload.update(diff_horde_updates)
            diff_horde_loss_cfg = DiffHordeLossConfig.model_validate(payload)

        trainer_cfg.losses.add_loss("diff_horde", diff_horde_loss_cfg)
        if teacher and teacher.enabled and teacher.mode.endswith(".sliced"):
            target_slice_names = {"ppo", "teacher_led", "student_led"}
        else:
            target_slice_names = {"default"}
        matching_slices = [
            slice_cfg for slice_cfg in tt.trajectory_isolation.slices if slice_cfg.name in target_slice_names
        ]
        if not matching_slices:
            raise ValueError(
                f"Cannot attach diff_horde to expected slices {sorted(target_slice_names)}. "
                f"Available slices: {[slice_cfg.name for slice_cfg in tt.trajectory_isolation.slices]}"
            )
        for target_slice in matching_slices:
            if "diff_horde" not in target_slice.losses:
                target_slice.losses.append("diff_horde")

    tt.stats_reporter.progress_metric = "env_game/cogs/aligned.junction.held"
    tt.stats_reporter.default_zero_metrics = tt.stats_reporter.default_zero_metrics + (
        "env_game/cogs/aligned.junction.held",
    )
    return tt


def _role_progress_metric(
    variants: str | Sequence[str] | None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
) -> tuple[str, str]:
    """Build a per-label-reward progress metric key and short display label.

    Mirrors the label construction in apply_reward_variants: canonical order,
    "objective" excluded.  The mission prefix and event-profile suffix are the
    defaults used by cogsguard_role.train.

    Returns (metric_key, display_label).
    """
    names: set[str] = set()
    for name in normalize_variant_names(variants):
        # Keep metric labels aligned with apply_reward_variants, which canonicalizes
        # objective_mine:<factor> to the base reward variant name.
        if name.startswith("objective_mine:"):
            names.add("objective_mine")
            continue
        names.add(name)
    suffix = ".".join(v for v in AVAILABLE_REWARD_VARIANTS if v != "objective" and v in names)
    label = f"cogsguard_{layout}.basic"
    if suffix:
        label = f"{label}.{suffix}"
    display = suffix or "reward"
    return f"env_per_label_rewards/{label}", display


def _resolve_role_teacher(teacher: TeacherConfig | dict[str, object] | None) -> TeacherConfig:
    if teacher is None:
        return TeacherConfig(policy_uri=None)
    if isinstance(teacher, dict):
        return TeacherConfig.model_validate(teacher)
    return teacher


def _make_role_train_tool(
    *,
    env: MettaGridConfig,
    layout: _CogsGuardLayout,
    teacher: TeacherConfig,
    policy_architecture: Optional[PolicyArchitecture],
    enable_vibe_actor_loss: bool = False,
) -> tools.TrainTool:
    curriculum = cc.bucketed(env)
    curriculum.add_bucket("game.map_builder.seed", [cc.Span(0, 1_000_000)])

    default_architecture = DefaultPolicyConfig(feature_extractor=BoxCNNFeatureExtractorConfig())
    trainer_cfg = TrainerConfig()
    training_env_cfg = TrainingEnvironmentConfig(curriculum=curriculum.to_curriculum())

    tt = tools.TrainTool(
        trainer=trainer_cfg,
        training_env=training_env_cfg,
        evaluator=EvaluatorConfig(simulations=simulations(env=env, layout=layout)),
        policy_assets={"learner0": PolicyAssetConfig(architecture=policy_architecture or default_architecture)},
    )

    if enable_vibe_actor_loss and _vibe_actions_enabled(training_env_cfg=training_env_cfg):
        _wire_vibe_actor_loss(trainer_cfg=trainer_cfg, slice_configs=tt.trajectory_isolation.slices)

    if teacher.enabled:
        scheduler_run_gates: list[LossRunGate] = []
        scheduler_rules: list[ScheduleRule] = []
        apply_teacher_phase(
            trainer_cfg=trainer_cfg,
            losses=trainer_cfg.losses,
            training_env_cfg=training_env_cfg,
            policy_assets=tt.policy_assets,
            scheduler_rules=scheduler_rules,
            scheduler_run_gates=scheduler_run_gates,
            teacher_cfg=teacher,
            trajectory_isolation=tt.trajectory_isolation,
        )
        tt.scheduler = SchedulerConfig(run_gates=scheduler_run_gates, rules=scheduler_rules)

    return tt


def miner(
    num_agents: int = 4,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    max_steps: int = 1000,
    variants: str | Sequence[str] | None = ("no_objective", "miner"),
    teacher: Optional[TeacherConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
) -> tools.TrainTool:
    """Train miner role with optional teacher supervision."""
    resolved_teacher = _resolve_role_teacher(teacher)

    resolved_variants, resolved_rewards = split_variants(variants)
    mission = _make_cogsguard_mission(
        layout=layout,
        num_agents=num_agents,
        max_steps=max_steps,
        variants=resolved_variants,
        clips_overrides={"disabled": True},
    )
    env = mission.make_env()
    env.game.actions.change_vibe.enabled = False
    if resolved_rewards:
        apply_reward_variants(env, variants=list(resolved_rewards))

    tt = _make_role_train_tool(
        env=env,
        layout=layout,
        teacher=resolved_teacher,
        policy_architecture=policy_architecture,
    )

    key, label = _role_progress_metric(variants, layout)
    tt.stats_reporter.progress_metric = key
    tt.stats_reporter.progress_metric_label = label
    return tt


def aligner(
    num_agents: int = 4,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    max_steps: int = 1000,
    variants: str | Sequence[str] | None = ("no_objective", "aligner"),
    teacher: Optional[TeacherConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
) -> tools.TrainTool:
    """Train aligner role with optional teacher supervision."""
    resolved_teacher = _resolve_role_teacher(teacher)

    resolved_variants, resolved_rewards = split_variants(variants)
    mission = _make_cogsguard_mission(
        layout=layout,
        num_agents=num_agents,
        max_steps=max_steps,
        variants=resolved_variants,
        clips_overrides={"disabled": True},
    )
    mission.cog.heart_limit = 3
    for team in mission.teams.values():
        team.initial_hearts = 120
    env = mission.make_env()
    env.game.actions.change_vibe.enabled = False
    if resolved_rewards:
        apply_reward_variants(env, variants=list(resolved_rewards))

    tt = _make_role_train_tool(
        env=env,
        layout=layout,
        teacher=resolved_teacher,
        policy_architecture=policy_architecture,
    )

    key, label = _role_progress_metric(variants, layout)
    tt.stats_reporter.progress_metric = key
    tt.stats_reporter.progress_metric_label = label
    return tt


def scout(
    num_agents: int = 4,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    max_steps: int = 1000,
    variants: str | Sequence[str] | None = ("no_objective", "scout"),
    teacher: Optional[TeacherConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
) -> tools.TrainTool:
    """Train scout role with optional teacher supervision."""
    resolved_teacher = _resolve_role_teacher(teacher)

    resolved_variants, resolved_rewards = split_variants(variants)
    mission = _make_cogsguard_mission(
        layout=layout,
        num_agents=num_agents,
        max_steps=max_steps,
        variants=resolved_variants,
        clips_overrides={"disabled": True},
    )
    env = mission.make_env()
    env.game.actions.change_vibe.enabled = False
    if resolved_rewards:
        apply_reward_variants(env, variants=list(resolved_rewards))

    tt = _make_role_train_tool(
        env=env,
        layout=layout,
        teacher=resolved_teacher,
        policy_architecture=policy_architecture,
    )

    key, label = _role_progress_metric(variants, layout)
    tt.stats_reporter.progress_metric = key
    tt.stats_reporter.progress_metric_label = label
    return tt


def scrambler(
    num_agents: int = 4,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    max_steps: int = 1000,
    variants: str | Sequence[str] | None = ("no_objective", "scrambler"),
    teacher: Optional[TeacherConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
) -> tools.TrainTool:
    """Train scrambler role with optional teacher supervision.

    Hubs start with 255 hearts. Clips invade normally.
    """
    resolved_teacher = _resolve_role_teacher(teacher)

    resolved_variants, resolved_rewards = split_variants(variants)
    mission = _make_cogsguard_mission(
        layout=layout,
        num_agents=num_agents,
        max_steps=max_steps,
        variants=list(resolved_variants or []),
    )
    for team in mission.teams.values():
        team.initial_hearts = 255
    env = mission.make_env()
    if resolved_rewards:
        apply_reward_variants(env, variants=list(resolved_rewards))

    tt = _make_role_train_tool(
        env=env,
        layout=layout,
        teacher=resolved_teacher,
        policy_architecture=policy_architecture,
        enable_vibe_actor_loss=True,
    )

    tt.stats_reporter.progress_metric = f"env_per_label_rewards/{env.label}"
    tt.stats_reporter.progress_metric_label = "scrambler"
    return tt


def evaluate(
    policy_uris: str | Sequence[str] | None = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> tools.EvaluateTool:
    if policy_uris is None:
        policy_uris = []
    elif not isinstance(policy_uris, str):
        policy_uris = list(policy_uris)
    return tools.EvaluateTool(
        simulations=simulations(variants=variants, layout=layout, max_steps=max_steps),
        policy_uris=policy_uris,
    )


def play(
    policy_uri: Optional[str] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    seed: int = 42,
) -> tools.PlayTool:
    """Interactive play with a policy."""
    return tools.PlayTool(
        sim=simulations(variants=variants, layout=layout, num_agents=num_agents, max_steps=max_steps)[0],
        policy_uri=policy_uri,
        seed=seed,
    )


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
    tool.trainer.total_timesteps = 3_000_000_000
    return tool


def evaluate_stub(*args: object, **kwargs: object) -> tools.StubTool:
    return tools.StubTool()


def sweep(
    sweep_name: str,
    variants: Sequence[str] = ("milestones", "credit", "penalize_vibe_change"),
    max_trials: int = 80,
    num_parallel_trials: int = 12,
) -> tools.SweepTool:
    # Fixed task setup; sweep only PPO/training hyperparameters.
    # Note: sweep suggestions are applied as post-construction overrides, so these
    # parameters override the tuned trainer defaults in train().
    parameters: list[dict[str, object]] = [
        {"variants": list(variants)},
        {"trainer.total_timesteps": 3_000_000_000},
        SP.param(
            "policy_assets.learner0.architecture.cortex_routed_adapter.trunk_lr_mult",
            D.LOG_NORMAL,
            min=0.1,
            max=10.0,
            search_center=_TUNED_PARAMS["routed_adapter.trunk_lr_mult"],
        ),
        SP.param(
            "trainer.optimizer.learning_rate",
            D.LOG_NORMAL,
            min=1e-4,
            max=3e-2,
            search_center=_TUNED_PARAMS["trainer.optimizer.learning_rate"],
        ),
        SP.param(
            "trainer.optimizer.momentum",
            D.UNIFORM,
            min=0.90,
            max=0.995,
            search_center=_TUNED_PARAMS["trainer.optimizer.momentum"],
        ),
        SP.param(
            "trainer.optimizer.weight_decay",
            D.LOG_NORMAL,
            min=1e-4,
            max=0.30,
            search_center=_TUNED_PARAMS["trainer.optimizer.weight_decay"],
        ),
        SP.param(
            "trainer.optimizer.eps",
            D.LOG_NORMAL,
            min=1e-8,
            max=1e-4,
            search_center=_TUNED_PARAMS["trainer.optimizer.eps"],
        ),
        SP.param(
            "trainer.optimizer.warmup_steps",
            D.INT_UNIFORM,
            min=500,
            max=5000,
            search_center=_TUNED_PARAMS["trainer.optimizer.warmup_steps"],
        ),
        SP.param(
            "trainer.sampling.prio_alpha",
            D.UNIFORM,
            min=0.0,
            max=1.0,
            search_center=_TUNED_PARAMS["trainer.sampling.prio_alpha"],
        ),
        SP.param(
            "trainer.sampling.prio_beta0",
            D.UNIFORM,
            min=0.0,
            max=1.0,
            search_center=_TUNED_PARAMS["trainer.sampling.prio_beta0"],
        ),
        SP.param(
            "trainer.advantage.gamma",
            D.UNIFORM,
            min=0.99,
            max=0.9999,
            search_center=_TUNED_PARAMS["trainer.advantage.gamma"],
        ),
        SP.param(
            "trainer.advantage.gae_lambda",
            D.UNIFORM,
            min=0.80,
            max=0.99,
            search_center=_TUNED_PARAMS["trainer.advantage.gae_lambda"],
        ),
        SP.param(
            "trainer.losses.ppo_actor.clip_coef",
            D.UNIFORM,
            min=0.10,
            max=0.60,
            search_center=_TUNED_PARAMS["trainer.losses.ppo_actor.clip_coef"],
        ),
        SP.param(
            "trainer.losses.ppo_actor.ent_coef",
            D.LOG_NORMAL,
            min=1e-4,
            max=2e-1,
            search_center=_TUNED_PARAMS["trainer.losses.ppo_actor.ent_coef"],
        ),
        SP.param(
            "trainer.losses.ppo_critic.vf_coef",
            D.UNIFORM,
            min=0.50,
            max=2.50,
            search_center=_TUNED_PARAMS["trainer.losses.ppo_critic.vf_coef"],
        ),
    ]

    return make_sweep(
        name=sweep_name,
        recipe="recipes.experiment.cogsguard",
        train_entrypoint="train_sweep",
        eval_entrypoint="evaluate_stub",
        metric_key="env_game/cogs/aligned.junction.held",
        search_space=parameters,
        cost_key="metric/total_time",
        max_trials=max_trials,
        num_parallel_trials=num_parallel_trials,
    )
