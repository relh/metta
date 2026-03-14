from __future__ import annotations

from mettagrid_sdk.sdk import BeliefMemoryRecord, GridPosition
from pydantic import BaseModel, Field


class TacticalBelief(BaseModel):
    belief_type: str
    summary: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    role_context: str | None = None
    importance: float = 0.0
    region_id: str | None = None
    location: GridPosition | None = None

    def as_memory_record(
        self,
        *,
        record_id: str,
        game: str,
        step: int | None,
        source: str = "reflection",
    ) -> BeliefMemoryRecord:
        return BeliefMemoryRecord(
            record_id=record_id,
            belief_type=self.belief_type,
            summary=self.summary,
            game=game,
            step=step,
            role_context=self.role_context,
            tags=self.tags,
            importance=self.importance,
            confidence=self.confidence,
            source=source,
            evidence_ids=self.evidence_ids,
            location=self.location,
            region_id=self.region_id,
        )
