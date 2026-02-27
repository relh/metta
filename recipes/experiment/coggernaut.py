"""CogsGuard Coggernaut: three-policy role training.

Three learnable policies trained in parallel via agent-range trajectory isolation:
- 4 agents -> miner policy slice
- 2 agents -> aligner policy slice
- 2 agents -> scrambler policy slice

Role assignment uses explicit role_id inventory + global observation.
"""

from __future__ import annotations

from typing import Optional, Sequence

from cortex.rl.feature_extractors import BoxCNNFeatureExtractorConfig

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.cogsguard_curriculum import EventProfile
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
from metta.sim.simulation_config import SimulationConfig
from metta.tools.utils.auto_config import auto_run_name
from mettagrid.config.game_value import inv
from mettagrid.config.mettagrid_config import MettaGridConfig
from recipes.experiment.cogsguard import (
    DEFAULT_INCLUDE_EVAL_MISSIONS,
    DEFAULT_INCLUDE_FIXED_MAPS,
    DEFAULT_LAYOUT,
    DEFAULT_NUM_AGENTS,
    _CogsGuardLayout,
)
from recipes.experiment.cogsguard import (
    make_env as _cg_make_env,
)
from recipes.experiment.cogsguard import (
    train as _cg_train,
)

_DEFAULT_EVENT_PROFILES: list[EventProfile] = [
    EventProfile(
        name="default",
        clips_overrides={},
        weather_overrides={},
    ),
]

_ROLE_ORDER: tuple[str, ...] = ("miner", "aligner", "scrambler", "scout")


def _with_role_conditional(variants: str | Sequence[str] | None) -> tuple[str, ...]:
    variant_names = [variants] if isinstance(variants, str) else list(variants or [])
    if "role_conditional" not in variant_names:
        variant_names.append("role_conditional")
    return tuple(variant_names)


def _apply_role_ids(env: MettaGridConfig, role_ids: Sequence[int]) -> None:
    """Assign explicit role_ids and vibes to agents, and set up role_id observation."""
    if not env.game.agents:
        raise ValueError("role_conditional requires env.game.agents (per-agent configs)")
    if len(env.game.agents) != len(role_ids):
        raise ValueError(f"Expected {len(role_ids)} agents for role assignment, got {len(env.game.agents)}")

    role_id_item = "role_id"
    if role_id_item not in env.game.resource_names:
        env.game.resource_names = [*env.game.resource_names, role_id_item]
    obs_key = f"inv:own:{role_id_item}"
    if obs_key not in env.game.obs.global_obs.obs:
        env.game.obs.global_obs.obs[obs_key] = inv(f"agent.{role_id_item}")
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
    run_name_prefix: str = "coggernaut_three_roles",
    role_ids: Sequence[int] = (0, 0, 0, 0, 1, 1, 2, 2),
    slice_configs: Sequence[tuple[str, tuple[int, int], str, str]] = (
        ("miner_slice", (0, 4), "miner_policy", "miner"),
        ("aligner_slice", (4, 6), "aligner_policy", "aligner"),
        ("scrambler_slice", (6, 8), "scrambler_policy", "scrambler"),
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


def play(
    policy_uris: list[str] | None = None,
    variants: str | Sequence[str] | None = ("no_objective", "randomize_spawns", "tin_man"),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = 1000,
    role_ids: Sequence[int] = (0, 0, 0, 0, 1, 1, 2, 2),
) -> tools.PlayTool:
    """Interactive play with coggernaut three-role policies."""
    env = _cg_make_env(variants=variants, layout=layout, num_agents=num_agents, max_steps=max_steps)
    _apply_role_ids(env, role_ids)
    apply_reward_variants(env, variants=["role_conditional"])
    sim = SimulationConfig(suite="cogsguard", name=f"coggernaut_{layout}", env=env)
    return tools.PlayTool(
        sim=sim,
        policy_uris=policy_uris or [],
        assignments=list(role_ids),
    )


def train(
    run: str | None = None,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    variants: str | Sequence[str] | None = ("no_objective", "randomize_spawns", "tin_man"),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = 1000,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
) -> tools.TrainTool:
    """CogsGuard Coggernaut: three learnable slices (miner/aligner/scrambler, 4+2+2)."""

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
