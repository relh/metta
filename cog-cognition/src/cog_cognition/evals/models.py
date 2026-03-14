from __future__ import annotations

from typing import Literal

from mettagrid_sdk.sdk import MettagridState
from pydantic import BaseModel, Field

from cog_cognition.planning import PlannerDecision

ProbeQuestion = Literal[
    "what_next",
    "abandon_triggers",
    "best_teammate_to_deposit_now",
    "why_not_target",
]


class BehavioralScenario(BaseModel):
    name: str
    states: list[MettagridState]


class ScenarioStepResult(BaseModel):
    step_index: int
    state_step: int | None = None
    decision: PlannerDecision


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
    plan_summary: str
    subtask_kind: str | None = None
    target_entity_id: str | None = None
    subject_entity_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
