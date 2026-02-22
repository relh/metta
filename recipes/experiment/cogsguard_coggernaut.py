"""CogsGuard Coggernaut: two-policy role training with gear-gated hearts.

Two learnable policies trained in parallel via agent-count trajectory isolation:
- 4 agents -> miner policy slice
- 4 agents -> aligner policy slice

Role assignment is vibe-based (no role_id resource). Agents must hold gear
before withdrawing hearts from hubs.
"""

from __future__ import annotations

from typing import Optional, Sequence

from cortex.rl.feature_extractors import BoxCNNFeatureExtractorConfig

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.cogsguard_curriculum import EventProfile
from cogames.cogs_vs_clips.config import CvCConfig
from cogames.cogs_vs_clips.reward_variants import apply_reward_variants
from metta.agent.policies.default import DefaultPolicyConfig
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
from mettagrid.config.filter import actorHasAnyOf
from mettagrid.config.mettagrid_config import MettaGridConfig
from recipes.experiment.cogsguard import (
    DEFAULT_INCLUDE_EVAL_MISSIONS,
    DEFAULT_INCLUDE_FIXED_MAPS,
    DEFAULT_LAYOUT,
    DEFAULT_NUM_AGENTS,
    _CogsGuardLayout,
)
from recipes.experiment.cogsguard import (
    train as _cg_train,
)

_DEFAULT_EVENT_PROFILES: list[EventProfile] = [
    EventProfile(
        name="no_clips",
        clips_overrides={"disabled": True},
        weather_overrides={},
    ),
]

_ROLE_ORDER: tuple[str, ...] = ("miner", "aligner", "scrambler", "scout")

_HEART_HANDLERS = ("get_heart", "get_and_make_heart", "get_last_heart")


def _with_role_conditional(variants: str | Sequence[str] | None) -> tuple[str, ...]:
    variant_names = [variants] if isinstance(variants, str) else list(variants or [])
    if "role_conditional" not in variant_names:
        variant_names.append("role_conditional")
    return tuple(variant_names)


def _apply_role_ids(env: MettaGridConfig, role_ids: Sequence[int]) -> None:
    """Assign vibes to agents based on role_ids for slice-aligned role assignment."""
    if not env.game.agents:
        raise ValueError("role_conditional requires env.game.agents (per-agent configs)")
    if len(env.game.agents) != len(role_ids):
        raise ValueError(f"Expected {len(role_ids)} agents for role assignment, got {len(env.game.agents)}")

    env.game.actions.change_vibe.enabled = False
    vibe_id_by_name = {name: idx for idx, name in enumerate(env.game.vibe_names)}
    for agent_cfg, role_id in zip(env.game.agents, role_ids, strict=False):
        role_name = _ROLE_ORDER[int(role_id) % len(_ROLE_ORDER)]
        role_vibe = vibe_id_by_name.get(role_name)
        if role_vibe is not None:
            agent_cfg.vibe = role_vibe


def _require_gear_for_hearts(env: MettaGridConfig) -> None:
    """Add a gear filter to hub heart-withdrawal handlers.

    Agents must hold any gear before they can pick up hearts.  This prevents
    random early hub-spam from draining team resources via heart
    manufacturing before agents have bought gear.
    """
    gear_filter = actorHasAnyOf(CvCConfig.GEAR)
    for object_name, object_cfg in env.game.objects.items():
        if not object_name.endswith(":hub"):
            continue
        for handler_name, handler in object_cfg.on_use_handlers.items():
            if handler_name in _HEART_HANDLERS:
                handler.filters.append(gear_filter)


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


def _set_gear_gate_for_hearts(curriculum: CurriculumConfig) -> None:
    def _apply(task_generator_config: object) -> None:
        if hasattr(task_generator_config, "env"):
            _require_gear_for_hearts(task_generator_config.env)
        if hasattr(task_generator_config, "task_generators"):
            for child in task_generator_config.task_generators:
                _apply(child)
        if hasattr(task_generator_config, "child_generator_config"):
            _apply(task_generator_config.child_generator_config)

    _apply(curriculum.task_generator)


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


def build_two_policy_role_train_tool(
    *,
    run: str | None = None,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    variants: str | Sequence[str] | None = ("no_objective",),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = 1000,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
    run_name_prefix: str = "coggernaut_two_roles",
    role_ids: Sequence[int] = (0, 0, 0, 0, 1, 1, 1, 1),
    slice_configs: Sequence[tuple[str, tuple[int, int], str, str]] = (
        ("miner_slice", (0, 4), "miner_policy", "miner"),
        ("aligner_slice", (4, 8), "aligner_policy", "aligner"),
    ),
) -> tools.TrainTool:
    if event_profiles is None:
        event_profiles = _DEFAULT_EVENT_PROFILES

    if num_agents != len(role_ids):
        raise ValueError(f"Expected num_agents={len(role_ids)} for this role split, got {num_agents}")
    total_agent_range = sum(hi - lo for _, (lo, hi), _, _ in slice_configs)
    if total_agent_range != num_agents:
        raise ValueError("Slice agent_ranges must cover all agents")

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

    default_architecture = DefaultPolicyConfig(feature_extractor=BoxCNNFeatureExtractorConfig())
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
    _set_gear_gate_for_hearts(tt.training_env.curriculum)
    _apply_role_conditional_rewards(tt.training_env.curriculum)

    tt.trainer.losses.losses.pop("ppo_actor", None)
    tt.trainer.losses.losses.pop("ppo_critic", None)
    for _, _, _, loss_suffix in slice_configs:
        tt.trainer.losses.add_loss(f"ppo_actor_{loss_suffix}", PPOActorConfig())
        tt.trainer.losses.add_loss(f"ppo_critic_{loss_suffix}", PPOCriticConfig())

    tt.trajectory_isolation = TrajectoryIsolationConfig(
        num_agents_per_env=num_agents,
        slices=[
            TrajectoryIsolationSliceConfig(
                name=slice_name,
                agent_range=agent_range,
                env_ratio=1.0,
                policies=[policy_name],
                losses=[f"ppo_actor_{loss_suffix}", f"ppo_critic_{loss_suffix}"],
            )
            for slice_name, agent_range, policy_name, loss_suffix in slice_configs
        ],
    )

    tt.trainer.total_timesteps = 2_000_000_000

    return tt


def train(
    run: str | None = None,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    variants: str | Sequence[str] | None = ("no_objective",),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = 1000,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
) -> tools.TrainTool:
    """CogsGuard Coggernaut: two learnable slices (miner/aligner, 4+4)."""

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
    )
