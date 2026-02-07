"""CogsGuard with future attribute prediction aux loss.

Identical to cogsguard.train except:
- Uses ViTFutureAttrPredConfig (3-layer MLP head for inventory prediction).
- Adds a FutureAttributePredictionLoss predicting 6 inventory attributes.
"""

from __future__ import annotations

from typing import Optional, Sequence

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cogs_vs_clips.cogsguard_curriculum import EventProfile
from metta.agent.policies.vit_future_attr_pred import ViTFutureAttrPredConfig
from metta.agent.policy import PolicyArchitecture
from metta.cogworks.curriculum.curriculum import CurriculumConfig
from metta.rl.loss.future_attribute_prediction import FutureAttributePredictionLossConfig
from metta.rl.training.teacher import TeacherConfig
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
) -> tools.TrainTool:
    """CogsGuard training with future-attribute-prediction aux loss."""

    # Build the base cogsguard TrainTool, swapping in the FAP architecture.
    default_architecture = ViTFutureAttrPredConfig(obs_shim_ignore_inventory_power_tokens=False)

    tt = _cg_train(
        curriculum=curriculum,
        policy_architecture=policy_architecture or default_architecture,
        teacher=teacher,
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

    # Add the future attribute prediction loss.
    tt.trainer.losses.add_loss("future_attr_pred", FutureAttributePredictionLossConfig())

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
