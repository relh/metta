from __future__ import annotations

from typing import Literal

from mettagrid_sdk.sdk import PlanMemoryRecord, RetrievedMemoryRecord
from mettagrid_sdk.sdk.state import GridPosition
from pydantic import BaseModel, Field


class SubtaskPlan(BaseModel):
    subtask_id: str
    kind: str
    summary: str
    target_entity_id: str | None = None
    target_owner: str | None = None
    target_position: GridPosition | None = None
    target_tags: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    failure_conditions: list[str] = Field(default_factory=list)


class AgendaPlan(BaseModel):
    agenda_id: str
    summary: str
    role_context: str | None = None
    created_step: int | None = None
    updated_step: int | None = None
    status: Literal["active", "completed", "abandoned"] = "active"
    active_subtask: SubtaskPlan
    supporting_memory_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def as_memory_record(self, *, game: str) -> PlanMemoryRecord:
        return PlanMemoryRecord(
            record_id=self.agenda_id,
            plan_type=self.active_subtask.kind,
            summary=self.summary,
            game=game,
            step=self.updated_step,
            role_context=self.role_context,
            tags=self.active_subtask.target_tags,
            importance=0.8,
            source="planner",
            evidence_ids=self.supporting_memory_ids,
            status=self.status,
            location=self.active_subtask.target_position,
        )


class ReactionTrigger(BaseModel):
    trigger_type: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class PlannerDecision(BaseModel):
    mode: Literal["continue", "replan"]
    plan: AgendaPlan
    triggers: list[ReactionTrigger] = Field(default_factory=list)
    supporting_memory: list[RetrievedMemoryRecord] = Field(default_factory=list)
