from __future__ import annotations

from typing import Literal

from mettagrid_sdk.sdk import MettagridState
from pydantic import BaseModel, Field

ProbeQuestion = Literal[
    "what_next",
    "best_teammate_to_deposit_now",
    "why_not_target",
]


class BehavioralScenario(BaseModel):
    name: str
    states: list[MettagridState]


class SemanticPolicyDecision(BaseModel):
    action_name: str
    role: str
    summary: str
    phase: str = ""
    target_kind: str = ""
    target_position: str = ""


class ScenarioStepResult(BaseModel):
    step_index: int
    state_step: int | None = None
    decision: SemanticPolicyDecision


class ScenarioResult(BaseModel):
    name: str
    steps: list[ScenarioStepResult] = Field(default_factory=list)


class InterviewProbeRequest(BaseModel):
    question_type: ProbeQuestion
    state: MettagridState
    target_entity_id: str | None = None


class InterviewProbeAnswer(BaseModel):
    question_type: ProbeQuestion
    answer: str
    role: str
    summary: str
    target_entity_id: str | None = None
    subject_entity_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
