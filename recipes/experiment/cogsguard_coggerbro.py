"""CogsGuard Coggerbro: two-policy training with annealed action-supervised loss.

Based on Coggernaut, but splits each policy's trajectories into two sub-slices:
- A1/B1: ppo_actor + ppo_critic + action_supervised (anneals from 95% -> 0%)
- A2/B2: ppo_actor + ppo_critic only              (anneals from  5% -> 100%)

Agent positions 0-3 belong to policy A, positions 4-7 to policy B.

Schedule:
- Steps 0 to 2.5B:   Hold at 95/5 split (action_supervised dominates).
- Steps 2.5B to 5.5B: Linearly anneal A1/B1 down to ~0%, A2/B2 up to ~100%.
"""

from __future__ import annotations

from typing import Optional, Sequence

from cortex.rl.feature_extractors import BoxCNNFeatureExtractorConfig

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.games.cogs_vs_clips.train.cogsguard_curriculum import EventProfile
from metta.agent.policies.default import DefaultPolicyConfig
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from metta.rl.loss.action_supervised import ActionSupervisedConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.loss.ppo_critic import PPOCriticConfig
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.training.scheduler import ScheduleRule
from metta.rl.training.teacher import TeacherConfig
from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
)
from metta.tools.utils.auto_config import auto_run_name
from recipes.experiment.coggernaut import (
    _DEFAULT_EVENT_PROFILES,
    _apply_role_conditional_rewards,
    _set_role_id_assignment,
    _with_role_conditional,
)
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

_HOLD_STEPS = 2_500_000_000
_ANNEAL_STEPS = 3_000_000_000
_TOTAL_STEPS = _HOLD_STEPS + _ANNEAL_STEPS

_INITIAL_SUPERVISED_RATIO = 0.95
_INITIAL_PURE_RATIO = 0.05
_FINAL_SUPERVISED_RATIO = 0.001
_FINAL_PURE_RATIO = 0.999


_TEACHER_POLICY_URI = "metta://policy/nlanky?miner=4&aligner=2&aligner=2&disable_role_switching=1"


def train(
    run: str | None = None,
    curriculum: Optional[CurriculumConfig] = None,
    policy_architecture: Optional[PolicyArchitecture] = None,
    teacher: TeacherConfig | dict[str, object] | None = None,
    variants: str | Sequence[str] | None = ("no_clips", "milestones", "no_objective"),
    layout: _CogsGuardLayout = DEFAULT_LAYOUT,
    num_agents: int = DEFAULT_NUM_AGENTS,
    max_steps: int = 1000,
    include_eval_missions: bool = DEFAULT_INCLUDE_EVAL_MISSIONS,
    include_fixed_maps: bool = DEFAULT_INCLUDE_FIXED_MAPS,
    max_steps_buckets: Sequence[int] | None = None,
    seed_span: cc.Span | None = None,
    event_profiles: Sequence[EventProfile] | None = None,
) -> tools.TrainTool:
    """CogsGuard Coggerbro: annealed action-supervised two-policy training."""
    if isinstance(teacher, dict):
        teacher = TeacherConfig.model_validate(teacher)

    if event_profiles is None:
        event_profiles = _DEFAULT_EVENT_PROFILES

    if num_agents != 8:
        raise ValueError(f"Coggerbro requires 8 agents (4+4 split), got {num_agents}")

    variants_with_role_conditional = _with_role_conditional(variants)
    variants_without_role_conditional = tuple(v for v in variants_with_role_conditional if v != "role_conditional")

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
        routed_adapter=None,
    )

    tt.training_env.supervisor_policy_uri = _TEACHER_POLICY_URI if teacher is None else teacher.policy_uri

    default_architecture = DefaultPolicyConfig(
        actor_hidden=128,
        critic_hidden=256,
        feature_extractor=BoxCNNFeatureExtractorConfig(
            output_dim=64,
        ),
    )
    policy_run_namespace = run or auto_run_name(prefix="coggerbro")
    tt.run = policy_run_namespace

    role_ids = (0, 0, 0, 0, 1, 1, 1, 1)

    tt.policy_assets = {
        "miner_policy": PolicyAssetConfig(
            run=f"{policy_run_namespace}.miner_policy",
            architecture=policy_architecture or default_architecture,
        ),
        "aligner_policy": PolicyAssetConfig(
            run=f"{policy_run_namespace}.aligner_policy",
            architecture=policy_architecture or default_architecture,
        ),
    }

    _set_role_id_assignment(tt.training_env.curriculum, role_ids)
    _apply_role_conditional_rewards(tt.training_env.curriculum)

    # -- Losses: per-side actor/critic + shared action_supervised per side --
    tt.trainer.losses.losses.pop("ppo_actor", None)
    tt.trainer.losses.losses.pop("ppo_critic", None)

    tt.trainer.losses.add_loss("ppo_actor_miner", PPOActorConfig())
    tt.trainer.losses.add_loss("ppo_critic_miner", PPOCriticConfig())
    tt.trainer.losses.add_loss("action_supervised_miner", ActionSupervisedConfig())

    tt.trainer.losses.add_loss("ppo_actor_aligner", PPOActorConfig())
    tt.trainer.losses.add_loss("ppo_critic_aligner", PPOCriticConfig())
    tt.trainer.losses.add_loss("action_supervised_aligner", ActionSupervisedConfig())

    # -- Trajectory isolation: 4 slices (A1, A2, B1, B2) --
    # A1/B1 start at 95% and anneal to ~0%; A2/B2 start at 5% and anneal to ~100%.
    anneal_rules = [
        ScheduleRule(
            target_path='slices["miner_supervised"].env_ratio',
            style="linear",
            start_value=_INITIAL_SUPERVISED_RATIO,
            end_value=_FINAL_SUPERVISED_RATIO,
            start_agent_step=_HOLD_STEPS,
            end_agent_step=_TOTAL_STEPS,
        ),
        ScheduleRule(
            target_path='slices["miner_pure"].env_ratio',
            style="linear",
            start_value=_INITIAL_PURE_RATIO,
            end_value=_FINAL_PURE_RATIO,
            start_agent_step=_HOLD_STEPS,
            end_agent_step=_TOTAL_STEPS,
        ),
        ScheduleRule(
            target_path='slices["aligner_supervised"].env_ratio',
            style="linear",
            start_value=_INITIAL_SUPERVISED_RATIO,
            end_value=_FINAL_SUPERVISED_RATIO,
            start_agent_step=_HOLD_STEPS,
            end_agent_step=_TOTAL_STEPS,
        ),
        ScheduleRule(
            target_path='slices["aligner_pure"].env_ratio',
            style="linear",
            start_value=_INITIAL_PURE_RATIO,
            end_value=_FINAL_PURE_RATIO,
            start_agent_step=_HOLD_STEPS,
            end_agent_step=_TOTAL_STEPS,
        ),
    ]

    tt.trajectory_isolation = TrajectoryIsolationConfig(
        num_agents_per_env=num_agents,
        slices=[
            # --- Policy A (agents 0-3) ---
            TrajectoryIsolationSliceConfig(
                name="miner_supervised",
                agent_range=(0, 4),
                env_ratio=_INITIAL_SUPERVISED_RATIO,
                policies=["miner_policy"],
                losses=["ppo_actor_miner", "ppo_critic_miner", "action_supervised_miner"],
            ),
            TrajectoryIsolationSliceConfig(
                name="miner_pure",
                agent_range=(0, 4),
                env_ratio=_INITIAL_PURE_RATIO,
                policies=["miner_policy"],
                losses=["ppo_actor_miner", "ppo_critic_miner"],
            ),
            # --- Policy B (agents 4-7) ---
            TrajectoryIsolationSliceConfig(
                name="aligner_supervised",
                agent_range=(4, 8),
                env_ratio=_INITIAL_SUPERVISED_RATIO,
                policies=["aligner_policy"],
                losses=["ppo_actor_aligner", "ppo_critic_aligner", "action_supervised_aligner"],
            ),
            TrajectoryIsolationSliceConfig(
                name="aligner_pure",
                agent_range=(4, 8),
                env_ratio=_INITIAL_PURE_RATIO,
                policies=["aligner_policy"],
                losses=["ppo_actor_aligner", "ppo_critic_aligner"],
            ),
        ],
        rules=anneal_rules,
    )

    tt.trainer.total_timesteps = _TOTAL_STEPS

    return tt
