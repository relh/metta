from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

AxisId = Literal[
    "experience_parallelism",
    "experience_quality",
    "loss_parallelism",
    "loss_signal_quality",
    "parameter_parallelism",
    "hyperparameter_quality",
]


class ImprovementCandidate(BaseModel):
    name: str
    summary: str
    expected_multiplier: float = Field(ge=1.0)


class AxisSpec(BaseModel):
    axis_id: AxisId
    index: int = Field(ge=1, le=6)
    title: str
    principle: str
    prior_multiplier: float = Field(ge=1.0)
    keywords: list[str]
    wins: list[ImprovementCandidate]


class ResearchPaperRecord(BaseModel):
    gid: str
    title: str
    notes: str = ""
    permalink_url: str
    created_at: str = ""
    modified_at: str = ""
    custom_fields: dict[str, str] = Field(default_factory=dict)
    paper_links: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    inferred_axis_scores: dict[str, float] = Field(default_factory=dict)

    def searchable_text(self) -> str:
        custom_values = " ".join(self.custom_fields.values())
        recommendations_text = " ".join(self.recommendations)
        links_text = " ".join(self.paper_links)
        return f"{self.title}\n{self.notes}\n{custom_values}\n{recommendations_text}\n{links_text}".lower()


class AxisPanel(BaseModel):
    axis_id: AxisId
    index: int
    title: str
    principle: str
    prior_multiplier: float
    projected_multiplier: float
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    evidence_titles: list[str]
    opportunity_score: float
    best_wins: list[ImprovementCandidate]


class DashboardSnapshot(BaseModel):
    generated_at: str
    combined_multiplier: float
    ranked_axes: list[AxisPanel]

    @classmethod
    def build(cls, combined_multiplier: float, ranked_axes: list[AxisPanel]) -> "DashboardSnapshot":
        return cls(
            generated_at=datetime.now(tz=UTC).isoformat(),
            combined_multiplier=combined_multiplier,
            ranked_axes=ranked_axes,
        )
