"""CogsGuard with role-conditioned, two-policy trajectory isolation.

This recipe demonstrates two learnable policies trained in parallel via
agent-range trajectory isolation:
- agents 0-3 -> miner policy slice
- agents 4-7 -> aligner policy slice

Reward routing is role-conditioned using ``role_conditional`` and explicit
per-agent ``inventory.initial.role_id`` assignment.
"""

from __future__ import annotations

from typing import Optional, Sequence

from cortex.config import RoutedAdapterConfig
from pydantic import Field, model_validator

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.cogsguard_curriculum import EventProfile
from cogames.cogs_vs_clips.reward_variants import apply_reward_variants
from metta.agent.policies.cnn_shared_critic import CnnSharedCriticConfig
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.loss.ppo_critic import PPOCriticConfig
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.training.scheduler import LossRunGate, SchedulerConfig, ScheduleRule
from metta.rl.training.teacher import TeacherConfig, apply_teacher_phase
from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
)
from metta.tools.utils.auto_config import auto_run_name
from mettagrid.base_config import Config
from mettagrid.config.game_value import inv
from mettagrid.config.mettagrid_config import MettaGridConfig
from recipes.experiment.cogsguard import (
    DEFAULT_INCLUDE_EVAL_MISSIONS,
    DEFAULT_INCLUDE_FIXED_MAPS,
    DEFAULT_LAYOUT,
    DEFAULT_MAX_STEPS,
    DEFAULT_NUM_AGENTS,
    _CogsGuardLayout,
)
from recipes.experiment.cogsguard import (
    evaluate as _cg_evaluate,
)
from recipes.experiment.cogsguard import (
    play as _cg_play,
)
from recipes.experiment.cogsguard import (
    train as _cg_train,
)

_DEFAULT_EVENT_PROFILES: list[EventProfile] = [
    EventProfile(
        name="no_clips_no_weather",
        clips_overrides={"disabled": True},
        weather_overrides={"day_deltas": {}, "night_deltas": {}},
    ),
]

_ROLE_ORDER: tuple[str, ...] = ("miner", "aligner", "scrambler", "scout")


class MarlbroSliceConfig(Config):
    name: str = Field(min_length=1)
    agent_range: tuple[int, int]
    policy_name: str = Field(min_length=1)
    loss_suffix: str = Field(min_length=1)
    route_slot_ids: tuple[int, ...] | None = None
    teacher: TeacherConfig | None = None

    @model_validator(mode="after")
    def _validate_fields(self) -> "MarlbroSliceConfig":
        TrajectoryIsolationSliceConfig(
            name=self.name,
            env_ratio=1.0,
            agent_range=self.agent_range,
            policies=[self.policy_name],
            losses=[self.loss_suffix],
            route_slot_ids=self.route_slot_ids,
        )
        return self


DEFAULT_MARLBRO_SLICE_CONFIGS: tuple[MarlbroSliceConfig, ...] = (
    MarlbroSliceConfig(name="miner_slice", agent_range=(0, 4), policy_name="miner_policy", loss_suffix="miner"),
    MarlbroSliceConfig(
        name="aligner_slice",
        agent_range=(4, 8),
        policy_name="aligner_policy",
        loss_suffix="aligner",
    ),
)


def _shared_policy_default_slice_configs() -> tuple[MarlbroSliceConfig, ...]:
    shared_policy_name = "shared_policy"
    return tuple(
        cfg.model_copy(
            update={
                "policy_name": shared_policy_name,
                "route_slot_ids": tuple(range(cfg.agent_range[0], cfg.agent_range[1])),
            }
        )
        for cfg in DEFAULT_MARLBRO_SLICE_CONFIGS
    )


def resolve_marlbro_slice_configs(
    slice_configs: Sequence[MarlbroSliceConfig | dict[str, object]],
) -> tuple[MarlbroSliceConfig, ...]:
    return tuple(
        slice_cfg if isinstance(slice_cfg, MarlbroSliceConfig) else MarlbroSliceConfig.model_validate(slice_cfg)
        for slice_cfg in slice_configs
    )


def _resolve_routed_adapter(
    routed_adapter: RoutedAdapterConfig | dict[str, object] | None,
    *,
    num_agents: int,
) -> RoutedAdapterConfig | None:
    if isinstance(routed_adapter, dict):
        routed_adapter_overrides = dict(routed_adapter)
        routed_adapter_overrides.setdefault("num_slots", num_agents)
        routed_adapter = RoutedAdapterConfig.model_validate(routed_adapter_overrides)
    if routed_adapter is not None and not routed_adapter.enabled:
        return None
    return routed_adapter


def _resolve_base_architecture(
    policy_architecture: PolicyArchitecture | None,
    routed_adapter: RoutedAdapterConfig | None,
) -> PolicyArchitecture:
    base_architecture = policy_architecture or CnnSharedCriticConfig()
    if routed_adapter is None:
        return base_architecture
    if not hasattr(base_architecture, "cortex_routed_adapter"):
        raise ValueError(
            "routed_adapter requires policy_architecture to expose cortex_routed_adapter. "
            "Pass an architecture that supports routed adapters."
        )
    if getattr(base_architecture, "cortex_routed_adapter", None) is not None:
        raise ValueError(
            "routed_adapter was provided, but policy_architecture already sets cortex_routed_adapter. "
            "Remove one of them."
        )
    return base_architecture.model_copy(update={"cortex_routed_adapter": routed_adapter})


def _with_agents_per_env_slice(
    policy_architecture: PolicyArchitecture,
    agents_per_env_slice: int,
) -> PolicyArchitecture:
    if hasattr(policy_architecture, "agents_per_env_slice"):
        return policy_architecture.model_copy(update={"agents_per_env_slice": agents_per_env_slice})
    return policy_architecture.model_copy(deep=True)


def _routed_adapter_num_slots(policy_architecture: PolicyArchitecture) -> int | None:
    routed_adapter = getattr(policy_architecture, "cortex_routed_adapter", None)
    if routed_adapter is None or not routed_adapter.enabled:
        return None
    return int(routed_adapter.num_slots)


def _with_role_conditional(variants: str | Sequence[str] | None) -> tuple[str, ...]:
    """Return the full variant list (for reward routing) and a filtered list for _cg_train.

    ``forced_role_vibes`` is excluded because ``_apply_role_ids`` handles role/vibe
    assignment directly — ``forced_role_vibes`` would overwrite the explicit role_ids
    with a cycling (0,1,2,3,…) pattern, breaking the slice-aligned assignment.
    ``role_conditional`` is excluded because ``_apply_role_conditional_rewards`` applies
    it after ``_apply_role_ids``.
    """
    variant_names = [variants] if isinstance(variants, str) else list(variants or [])
    if "role_conditional" not in variant_names:
        variant_names.append("role_conditional")
    return tuple(variant_names)


def _apply_role_ids(env: MettaGridConfig, role_ids: Sequence[int]) -> None:
    """Assign explicit role_ids and vibes to agents, and set up role_id observation.

    This replaces ``forced_role_vibes`` for the marlbro recipe so that role
    assignment is slice-aligned (e.g. 0,0,0,0,1,1,1,1) rather than cycling.
    """
    if not env.game.agents:
        raise ValueError("role_conditional requires env.game.agents (per-agent configs)")
    if len(env.game.agents) != len(role_ids):
        raise ValueError(f"Expected {len(role_ids)} agents for role assignment, got {len(env.game.agents)}")

    # Add role_id as a resource and global observation (mirrors forced_role_vibes setup).
    role_id_item = "role_id"
    if role_id_item not in env.game.resource_names:
        env.game.resource_names = [*env.game.resource_names, role_id_item]
    global_obs = list(env.game.obs.global_obs.obs)
    role_obs_token = inv(f"agent.{role_id_item}")
    if role_obs_token not in global_obs:
        global_obs.append(role_obs_token)
        env.game.obs.global_obs.obs = global_obs
    env.game.actions.change_vibe.enabled = False

    vibe_id_by_name = {name: idx for idx, name in enumerate(env.game.vibe_names)}
    for agent_cfg, role_id in zip(env.game.agents, role_ids, strict=False):
        role_name = _ROLE_ORDER[int(role_id) % len(_ROLE_ORDER)]
        role_vibe = vibe_id_by_name.get(role_name)
        agent_cfg.inventory.initial = {**agent_cfg.inventory.initial, role_id_item: role_id}
        if role_vibe is not None:
            agent_cfg.vibe = role_vibe


def _set_role_id_assignment(curriculum: CurriculumConfig, role_ids: Sequence[int]) -> None:
    def _apply(task_generator_config: object) -> None:
        if hasattr(task_generator_config, "env"):
            _apply_role_ids(task_generator_config.env, role_ids)
        if hasattr(task_generator_config, "task_generators"):
            for child in task_generator_config.task_generators:
                _apply(child)
        if hasattr(task_generator_config, "child_generator_config"):
            _apply(task_generator_config.child_generator_config)

    _apply(curriculum.task_generator)


def build_two_policy_role_train_tool(
    *,
    run: str | None = None,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    variants: str | Sequence[str] | None = ("milestones",),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
    routed_adapter: RoutedAdapterConfig | dict[str, object] | None = None,
    run_name_prefix: str = "marlbro_two_roles",
    role_ids: Sequence[int] = (0, 0, 0, 0, 1, 1, 1, 1),
    slice_configs: Sequence[MarlbroSliceConfig | dict[str, object]] = DEFAULT_MARLBRO_SLICE_CONFIGS,
) -> tools.TrainTool:
    """Build a two-policy role-conditioned training tool.

    ``slice_configs`` controls per-slice policy assignment, route slots, and optional teacher config.
    """
    if event_profiles is None:
        event_profiles = _DEFAULT_EVENT_PROFILES
    if isinstance(teacher, dict):
        teacher = TeacherConfig.model_validate(teacher)

    resolved_routed_adapter = _resolve_routed_adapter(routed_adapter, num_agents=num_agents)
    effective_slice_configs: Sequence[MarlbroSliceConfig | dict[str, object]] = slice_configs
    if resolved_routed_adapter is not None and slice_configs is DEFAULT_MARLBRO_SLICE_CONFIGS:
        effective_slice_configs = _shared_policy_default_slice_configs()
    resolved_slice_configs = resolve_marlbro_slice_configs(effective_slice_configs)
    resolved_policy_architecture = _resolve_base_architecture(
        policy_architecture=policy_architecture,
        routed_adapter=resolved_routed_adapter,
    )

    if num_agents != len(role_ids):
        raise ValueError(f"Expected num_agents={len(role_ids)} for this role split, got {num_agents}")
    total_agent_range = sum(cfg.agent_range[1] - cfg.agent_range[0] for cfg in resolved_slice_configs)
    if total_agent_range != num_agents:
        raise ValueError("Slice agent_ranges must cover all agents")
    slice_names = [cfg.name for cfg in resolved_slice_configs]
    if len(set(slice_names)) != len(slice_names):
        raise ValueError(f"Slice names must be unique, got {slice_names}")
    loss_suffixes = [cfg.loss_suffix for cfg in resolved_slice_configs]
    if len(set(loss_suffixes)) != len(loss_suffixes):
        raise ValueError(f"Slice loss_suffix values must be unique, got {loss_suffixes}")
    for cfg in resolved_slice_configs:
        teacher_cfg = cfg.teacher
        if teacher_cfg is None or not teacher_cfg.enabled:
            continue
        if teacher_cfg.mode.endswith(".sliced"):
            raise ValueError(f"Slice '{cfg.name}' teacher mode '{teacher_cfg.mode}' is unsupported; use mixed mode")
        if teacher_cfg.mode.startswith("scripted."):
            raise ValueError(
                f"Slice '{cfg.name}' teacher mode '{teacher_cfg.mode}' is unsupported for per-slice teachers; "
                "use learned kickstarter modes"
            )
    if (
        teacher is not None
        and teacher.enabled
        and any(cfg.teacher is not None and cfg.teacher.enabled for cfg in resolved_slice_configs)
    ):
        raise ValueError("Cannot combine top-level teacher with slice-level teachers")
    if teacher is not None and teacher.enabled and teacher.mode.endswith(".sliced"):
        raise ValueError(f"Top-level teacher mode '{teacher.mode}' is unsupported for marlbro; use mixed mode")

    variants_with_role_conditional = _with_role_conditional(variants)
    variants_without_role_conditional = tuple(
        variant for variant in variants_with_role_conditional if variant != "role_conditional"
    )

    tt = _cg_train(
        curriculum=curriculum,
        policy_architecture=resolved_policy_architecture,
        teacher=None,
        variants=variants_without_role_conditional,
        layout=layout,
        num_agents=num_agents,
        max_steps=max_steps,
        include_eval_missions=include_eval_missions,
        include_fixed_maps=include_fixed_maps,
        max_steps_buckets=max_steps_buckets,
        seed_span=seed_span,
        event_profiles=event_profiles,
    )

    policy_run_namespace = run or auto_run_name(prefix=run_name_prefix)
    tt.run = policy_run_namespace

    policy_slice_agents: dict[str, int] = {}
    for cfg in resolved_slice_configs:
        lo, hi = cfg.agent_range
        slice_agent_count = hi - lo
        if cfg.policy_name in policy_slice_agents and policy_slice_agents[cfg.policy_name] != slice_agent_count:
            raise ValueError(
                f"Policy '{cfg.policy_name}' is used by slices with inconsistent widths "
                f"({policy_slice_agents[cfg.policy_name]} vs {slice_agent_count})"
            )
        policy_slice_agents[cfg.policy_name] = slice_agent_count

    base_architecture = resolved_policy_architecture
    tt.policy_assets = {
        policy_name: PolicyAssetConfig(
            run=f"{policy_run_namespace}.{policy_name}",
            architecture=_with_agents_per_env_slice(base_architecture, slice_agent_count),
        )
        for policy_name, slice_agent_count in policy_slice_agents.items()
    }
    for cfg in resolved_slice_configs:
        if cfg.route_slot_ids is None:
            continue
        arch = tt.policy_assets[cfg.policy_name].architecture
        if arch is None:
            raise ValueError(f"Slice '{cfg.name}' route_slot_ids requires a policy architecture")
        num_slots = _routed_adapter_num_slots(arch)
        if num_slots is None:
            raise ValueError(
                f"Slice '{cfg.name}' route_slot_ids requires policy '{cfg.policy_name}' to enable cortex_routed_adapter"
            )
        invalid_slots = [slot_id for slot_id in cfg.route_slot_ids if int(slot_id) >= num_slots]
        if invalid_slots:
            raise ValueError(
                f"Slice '{cfg.name}' route_slot_ids {invalid_slots} are out of range for num_slots={num_slots}"
            )

    _set_role_id_assignment(tt.training_env.curriculum, role_ids)
    _apply_aligner_training_settings(tt.training_env.curriculum)
    _apply_role_conditional_rewards(tt.training_env.curriculum)

    tt.trainer.losses.losses.pop("ppo_actor", None)
    tt.trainer.losses.losses.pop("ppo_critic", None)
    for cfg in resolved_slice_configs:
        loss_suffix = cfg.loss_suffix
        tt.trainer.losses.add_loss(f"ppo_actor_{loss_suffix}", PPOActorConfig())
        tt.trainer.losses.add_loss(f"ppo_critic_{loss_suffix}", PPOCriticConfig())

    tt.trajectory_isolation = TrajectoryIsolationConfig(
        num_agents_per_env=num_agents,
        slices=[
            TrajectoryIsolationSliceConfig(
                name=cfg.name,
                agent_range=cfg.agent_range,
                env_ratio=1.0,
                policies=[cfg.policy_name],
                losses=[f"ppo_actor_{cfg.loss_suffix}", f"ppo_critic_{cfg.loss_suffix}"],
                route_slot_ids=cfg.route_slot_ids,
            )
            for cfg in resolved_slice_configs
        ],
    )

    scheduler_run_gates: list[LossRunGate] = []
    scheduler_rules: list[ScheduleRule] = []
    for cfg in resolved_slice_configs:
        teacher_cfg = cfg.teacher
        if teacher_cfg is None or not teacher_cfg.enabled:
            continue
        apply_teacher_phase(
            trainer_cfg=tt.trainer,
            losses=tt.trainer.losses,
            policy_assets=tt.policy_assets,
            training_env_cfg=tt.training_env,
            scheduler_rules=scheduler_rules,
            scheduler_run_gates=scheduler_run_gates,
            teacher_cfg=teacher_cfg,
            trajectory_isolation=tt.trajectory_isolation,
            name_prefix=f"{cfg.name}_",
            target_slice_name=cfg.name,
        )
    if teacher is not None and teacher.enabled:
        if teacher.mode.endswith(".mixed"):
            for cfg in resolved_slice_configs:
                apply_teacher_phase(
                    trainer_cfg=tt.trainer,
                    losses=tt.trainer.losses,
                    policy_assets=tt.policy_assets,
                    training_env_cfg=tt.training_env,
                    scheduler_rules=scheduler_rules,
                    scheduler_run_gates=scheduler_run_gates,
                    teacher_cfg=teacher,
                    trajectory_isolation=tt.trajectory_isolation,
                    name_prefix=f"{cfg.name}_",
                    target_slice_name=cfg.name,
                )
        else:
            apply_teacher_phase(
                trainer_cfg=tt.trainer,
                losses=tt.trainer.losses,
                policy_assets=tt.policy_assets,
                training_env_cfg=tt.training_env,
                scheduler_rules=scheduler_rules,
                scheduler_run_gates=scheduler_run_gates,
                teacher_cfg=teacher,
                trajectory_isolation=tt.trajectory_isolation,
            )
    if scheduler_run_gates or scheduler_rules:
        tt.scheduler = SchedulerConfig(run_gates=scheduler_run_gates, rules=scheduler_rules)
    return tt


def _apply_role_conditional_rewards(curriculum: CurriculumConfig) -> None:
    def _apply(task_generator_config: object) -> None:
        if hasattr(task_generator_config, "env"):
            apply_reward_variants(task_generator_config.env, variants=["role_conditional"])
        if hasattr(task_generator_config, "task_generators"):
            for child in task_generator_config.task_generators:
                _apply(child)
        if hasattr(task_generator_config, "child_generator_config"):
            _apply(task_generator_config.child_generator_config)

    _apply(curriculum.task_generator)


def _apply_aligner_training_settings(curriculum: CurriculumConfig) -> None:
    def _apply(task_generator_config: object) -> None:
        if hasattr(task_generator_config, "env"):
            env = task_generator_config.env
            for agent_cfg in env.game.agents:
                agent_cfg.inventory.limits["heart"].max = 3
            for object_name, object_cfg in env.game.objects.items():
                if object_name.endswith(":hub"):
                    object_cfg.inventory.initial["heart"] = 120
        if hasattr(task_generator_config, "task_generators"):
            for child in task_generator_config.task_generators:
                _apply(child)
        if hasattr(task_generator_config, "child_generator_config"):
            _apply(task_generator_config.child_generator_config)

    _apply(curriculum.task_generator)


def train(
    run: str | None = None,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: Optional[TeacherConfig] = None,
    routed_adapter: RoutedAdapterConfig | dict[str, object] | None = None,
    supervisor_policy_uri: str = "metta://policy/nlanky",
    teacher_led_proportion: float = 0.0,
    variants: str | Sequence[str] | None = ("milestones",),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
) -> tools.TrainTool:
    """CogsGuard with two learnable slices (miner/aligner, 4+4)."""

    _ = supervisor_policy_uri, teacher_led_proportion
    return build_two_policy_role_train_tool(
        run=run,
        curriculum=curriculum,
        policy_architecture=policy_architecture,
        teacher=teacher,
        routed_adapter=routed_adapter,
        variants=variants,
        layout=layout,
        num_agents=num_agents,
        max_steps=max_steps,
        include_eval_missions=include_eval_missions,
        include_fixed_maps=include_fixed_maps,
        max_steps_buckets=max_steps_buckets,
        seed_span=seed_span,
        event_profiles=event_profiles,
        run_name_prefix="marlbro_two_roles",
        role_ids=(0, 0, 0, 0, 1, 1, 1, 1),
    )


def evaluate(
    policy_uris: str | Sequence[str] | None = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
) -> tools.EvaluateTool:
    return _cg_evaluate(policy_uris=policy_uris, variants=variants, layout=layout)


def play(
    policy_uri: Optional[str] = None,
    variants: str | Sequence[str] | None = None,
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
) -> tools.PlayTool:
    return _cg_play(policy_uri=policy_uri, variants=variants, layout=layout)
