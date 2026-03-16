from __future__ import annotations

import importlib

from cog_cognition.evals.harness import PlannerEvaluationHarness
from cog_cognition.evals.models import (
    BehavioralScenario,
    InterviewProbeAnswer,
    InterviewProbeRequest,
    ScenarioResult,
    ScenarioStepResult,
)
from cog_cognition.evals.semantic_models import (
    SemanticBehavioralScenario,
    SemanticInterviewProbeAnswer,
    SemanticInterviewProbeRequest,
    SemanticPolicyDecision,
    SemanticProbeQuestion,
    SemanticScenarioResult,
    SemanticScenarioStepResult,
)

__all__ = [
    "BehavioralScenario",
    "InterviewProbeAnswer",
    "InterviewProbeRequest",
    "PlannerEvaluationHarness",
    "SemanticBehavioralScenario",
    "SemanticInterviewProbeAnswer",
    "SemanticInterviewProbeRequest",
    "SemanticPolicyDecision",
    "SemanticPolicyEvaluationHarness",
    "SemanticProbeQuestion",
    "SemanticScenarioResult",
    "SemanticScenarioStepResult",
    "ScenarioResult",
    "ScenarioStepResult",
]


def __getattr__(name: str) -> object:
    if name == "SemanticPolicyEvaluationHarness":
        return importlib.import_module("cog_cognition.evals.semantic_policy").SemanticPolicyEvaluationHarness
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
