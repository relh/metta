"""CogsGuard with role-conditioned, two-policy trajectory isolation.

This recipe demonstrates two learnable policies trained in parallel via
agent-count trajectory isolation:
- 4 agents -> miner policy slice
- 4 agents -> aligner policy slice

Reward routing is role-conditioned using ``role_conditional`` and explicit
per-agent ``inventory.initial.role_id`` assignment.
"""

from __future__ import annotations

from typing import Optional, Sequence

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
from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
)
from metta.tools.utils.auto_config import auto_run_name
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
    variants: str | Sequence[str] | None = ("milestones",),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
    run_name_prefix: str = "marlbro_two_roles",
    role_ids: Sequence[int] = (0, 0, 0, 0, 1, 1, 1, 1),
    slice_configs: Sequence[tuple[str, int, str, str]] = (
        ("miner_slice", 4, "miner_policy", "miner"),
        ("aligner_slice", 4, "aligner_policy", "aligner"),
    ),
) -> tools.TrainTool:
    if event_profiles is None:
        event_profiles = _DEFAULT_EVENT_PROFILES

    if num_agents != len(role_ids):
        raise ValueError(f"Expected num_agents={len(role_ids)} for this role split, got {num_agents}")
    if sum(agent_count for _, agent_count, _, _ in slice_configs) != num_agents:
        raise ValueError("Slice agent counts must sum to num_agents")

    variants_with_role_conditional = _with_role_conditional(variants)
    variants_without_role_conditional = tuple(
        variant for variant in variants_with_role_conditional if variant != "role_conditional"
    )

    tt = _cg_train(
        curriculum=curriculum,
        policy_architecture=policy_architecture,
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

    default_architecture = CnnSharedCriticConfig()
    policy_run_namespace = run or auto_run_name(prefix=run_name_prefix)
    tt.run = policy_run_namespace

    policy_names = list(dict.fromkeys(policy_name for _, _, policy_name, _ in slice_configs))
    tt.policy_assets = {
        policy_name: PolicyAssetConfig(
            run=f"{policy_run_namespace}.{policy_name}",
            architecture=policy_architecture or default_architecture,
        )
        for policy_name in policy_names
    }

    _set_role_id_assignment(tt.training_env.curriculum, role_ids)
    _apply_aligner_training_settings(tt.training_env.curriculum)
    _apply_role_conditional_rewards(tt.training_env.curriculum)

    tt.trainer.losses.losses.pop("ppo_actor", None)
    tt.trainer.losses.losses.pop("ppo_critic", None)
    for _, _, _, loss_suffix in slice_configs:
        tt.trainer.losses.add_loss(f"ppo_actor_{loss_suffix}", PPOActorConfig())
        tt.trainer.losses.add_loss(f"ppo_critic_{loss_suffix}", PPOCriticConfig())

    tt.trajectory_isolation = TrajectoryIsolationConfig(
        slicing_method="agent_count",
        num_agents_per_env=num_agents,
        slices=[
            TrajectoryIsolationSliceConfig(
                name=slice_name,
                agent_count=agent_count,
                policies=[policy_name],
                losses=[f"ppo_actor_{loss_suffix}", f"ppo_critic_{loss_suffix}"],
            )
            for slice_name, agent_count, policy_name, loss_suffix in slice_configs
        ],
    )
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
    supervisor_policy_uri: str = "metta://policy/planky",
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
        slice_configs=(
            ("miner_slice", 4, "miner_policy", "miner"),
            ("aligner_slice", 4, "aligner_policy", "aligner"),
        ),
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
