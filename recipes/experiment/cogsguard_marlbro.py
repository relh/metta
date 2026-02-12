"""CogsGuard with agent-count trajectory isolation for MARLBRO experiments.

Based on the standard cogsguard recipe with:
- Agent-count trajectory isolation (7+1 split across 8 agents per env).
- Supervisor policy for scripted teacher actions.

The ``scripted`` slice (7 agents) unconditionally follows the teacher — its
actions are overwritten with teacher actions (no training loss).
The ``learned_policy`` slice (1 agent) trains with ppo_actor, ppo_critic, and
an action_supervised loss.
"""

from __future__ import annotations

from typing import Optional, Sequence

from cortex.rl.feature_extractors import TokenPerceiverFeatureExtractorConfig

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.cogsguard_curriculum import EventProfile
from metta.agent.policies.core_policy import CorePolicyConfig
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from metta.rl.loss.action_supervised import ActionSupervisedConfig
from metta.rl.loss.teacher_action_override import TeacherActionOverrideConfig
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
)
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


def train(
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
    """CogsGuard with agent-count trajectory isolation (7+1 split)."""

    if event_profiles is None:
        event_profiles = _DEFAULT_EVENT_PROFILES

    # Build base cogsguard TrainTool without a teacher—we handle supervisor
    # URI, losses, and trajectory isolation manually below.
    tt = _cg_train(
        curriculum=curriculum,
        policy_architecture=policy_architecture,
        teacher=None,
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

    # Explicit single trainable policy, created from scratch.
    default_architecture = CorePolicyConfig(
        feature_extractor=TokenPerceiverFeatureExtractorConfig(ignore_inventory_power_tokens=False)
    )
    tt.policy_assets = {
        "learner0": PolicyAssetConfig(architecture=policy_architecture or default_architecture),
    }

    # Set the supervisor policy URI so the environment provides scripted
    # teacher actions (same wiring as teacher.py apply_teacher_phase).
    tt.training_env.supervisor_policy_uri = supervisor_policy_uri

    # Scripted slice: override student actions with teacher actions (no loss).
    tt.trainer.losses.add_loss(
        "teacher_override_scripted",
        TeacherActionOverrideConfig(),
    )
    # Learned policy slice: action_supervised loss for gradient signal.
    tt.trainer.losses.add_loss(
        "action_supervised_learned",
        ActionSupervisedConfig(teacher_led_proportion=teacher_led_proportion),
    )

    # Agent-count trajectory isolation: within each environment the first 7
    # agent slots go to the scripted slice and the last 1 goes to the
    # learned_policy slice.  Slices are allocated in definition order
    # (guaranteed by _build_plan_agent_count).
    tt.trajectory_isolation = TrajectoryIsolationConfig(
        slicing_method="agent_count",
        num_agents_per_env=num_agents,
        slices=[
            TrajectoryIsolationSliceConfig(
                name="scripted",
                agent_count=num_agents - 1,
                policies=["learner0"],
                losses=["teacher_override_scripted"],
            ),
            TrajectoryIsolationSliceConfig(
                name="learned_policy",
                agent_count=1,
                policies=["learner0"],
                losses=["ppo_actor", "ppo_critic", "action_supervised_learned"],
            ),
        ],
    )

    return tt


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
