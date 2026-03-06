from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

AxisId = Literal[
    "experience_parallelism",
    "experience_quality",
    "loss_parallelism",
    "loss_signal_quality",
    "parameter_parallelism",
    "hyperparameter_quality",
]

ExecutionMetricId = Literal[
    "simplicity",
    "time_to_implement",
    "failure_likelihood",
    "dependency_load",
    "measurement_speed",
    "reversibility",
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
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    evidence_titles: list[str]
    opportunity_score: float
    best_wins: list[ImprovementCandidate]


class DashboardSnapshot(BaseModel):
    generated_at: str
    ranked_axes: list[AxisPanel]

    @classmethod
    def build(cls, ranked_axes: list[AxisPanel]) -> "DashboardSnapshot":
        return cls(
            generated_at=datetime.now(tz=UTC).isoformat(),
            ranked_axes=ranked_axes,
        )


class TaskExecutionScores(BaseModel):
    simplicity: float = Field(ge=0.0, le=1.0)
    time_to_implement: float = Field(ge=0.0, le=1.0)
    failure_likelihood: float = Field(ge=0.0, le=1.0)
    dependency_load: float = Field(ge=0.0, le=1.0)
    measurement_speed: float = Field(ge=0.0, le=1.0)
    reversibility: float = Field(ge=0.0, le=1.0)


class LLMTaskScores(BaseModel):
    axis_scores: dict[AxisId, float]
    execution_scores: TaskExecutionScores
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class LLMTaskScoreCacheEntry(BaseModel):
    gid: str
    modified_at: str
    model: str
    rubric_version: str
    scored_at: str
    scores: LLMTaskScores


class RankedTask(BaseModel):
    gid: str
    title: str
    permalink_url: str
    axis_scores: dict[AxisId, float]
    execution_scores: TaskExecutionScores
    impact_score: float = Field(ge=0.0, le=1.0)
    feasibility_score: float = Field(ge=0.0, le=1.0)
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    priority_score: float = Field(ge=0.0, le=1.0)
    top_axes: list[AxisId]


class TaskRankingSnapshot(BaseModel):
    generated_at: str
    tasks_scored: int = Field(ge=0)
    impact_metrics: list[AxisId]
    execution_metrics: list[ExecutionMetricId]
    ranked_tasks: list[RankedTask]

    @classmethod
    def build(
        cls,
        tasks_scored: int,
        impact_metrics: list[AxisId],
        execution_metrics: list[ExecutionMetricId],
        ranked_tasks: list[RankedTask],
    ) -> "TaskRankingSnapshot":
        return cls(
            generated_at=datetime.now(tz=UTC).isoformat(),
            tasks_scored=tasks_scored,
            impact_metrics=impact_metrics,
            execution_metrics=execution_metrics,
            ranked_tasks=ranked_tasks,
        )


class PipelineFamilyShare(BaseModel):
    family: str
    count: int = Field(ge=0)
    share: float = Field(ge=0.0, le=1.0)


class TrainingExperimentMetrics(BaseModel):
    running_now: int = Field(ge=0)
    running_recent_7d: int = Field(ge=0)
    running_stale_gt_14d: int = Field(ge=0)
    finished_recent_7d: int = Field(ge=0)
    crashed_recent_7d: int = Field(ge=0)
    starts_recent_7d_lower_bound: int = Field(ge=0)
    crash_rate_recent_7d: float = Field(ge=0.0, le=1.0)


class SearchCoverageMetrics(BaseModel):
    unique_families_30d: int = Field(ge=0)
    top_family_share_30d: float = Field(ge=0.0, le=1.0)
    family_entropy_30d: float = Field(ge=0.0, le=1.0)
    dominant_families_30d: list[PipelineFamilyShare]


class MeaningfulResultMetrics(BaseModel):
    metric_keys_considered: list[str]
    metric_presence_counts: dict[str, int]
    primary_metric: str = ""
    primary_metric_coverage_ratio: float = Field(ge=0.0, le=1.0)
    measurable: bool
    meaningful_events_7d: int = Field(ge=0)
    meaningful_events_30d: int = Field(ge=0)
    weekly_meaningful_rate: float = Field(ge=0.0)
    threshold_definition: str


PipelineAssessmentStatus = Literal["good", "thin", "critical", "not_measurable"]


class PipelineAssessment(BaseModel):
    status: PipelineAssessmentStatus
    headline: str
    detail: str


class TrainingPipelineAssessments(BaseModel):
    concurrent_experiments: PipelineAssessment
    search_space_coverage: PipelineAssessment
    meaningful_result_cadence: PipelineAssessment


class TrainingPipelineSnapshot(BaseModel):
    generated_at: str
    available: bool
    source: str
    notes: list[str] = Field(default_factory=list)
    experiments: Optional[TrainingExperimentMetrics] = None
    search_coverage: Optional[SearchCoverageMetrics] = None
    meaningful_results: Optional[MeaningfulResultMetrics] = None
    assessments: Optional[TrainingPipelineAssessments] = None

    @classmethod
    def unavailable(cls, source: str, note: str) -> "TrainingPipelineSnapshot":
        return cls(
            generated_at=datetime.now(tz=UTC).isoformat(),
            available=False,
            source=source,
            notes=[note],
        )


class ResearchFunnelStages(BaseModel):
    paper_selected: int = Field(ge=0)
    author_repo_found: int = Field(ge=0)
    implemented_in_metta: int = Field(ge=0)
    paper_to_repo_conversion: float = Field(ge=0.0, le=1.0)
    repo_to_impl_conversion: float = Field(ge=0.0, le=1.0)


class ResearchFunnelSnapshot(BaseModel):
    generated_at: str
    tasks_total: int = Field(ge=0)
    llm_scored_tasks: int = Field(ge=0)
    llm_coverage: float = Field(ge=0.0, le=1.0)
    status_counts: dict[str, int]
    paper_signal_tasks: int = Field(ge=0)
    repo_signal_tasks: int = Field(ge=0)
    implemented_tasks: int = Field(ge=0)
    paper_repo_tasks: int = Field(ge=0)
    paper_repo_implemented_tasks: int = Field(ge=0)
    stages: ResearchFunnelStages


class CogsguardTrainDefaultsAudit(BaseModel):
    command: str
    default_layout: str
    default_num_agents: int = Field(ge=1)
    default_max_steps: int = Field(ge=1)
    default_policy_assets: list[str]
    default_losses: list[str]
    conditional_losses: list[str]
    progress_metric: str


class MultiPolicySupportAudit(BaseModel):
    supported: bool
    mechanism: str
    evidence_paths: list[str]
    example_recipe: str
    example_policies: list[str]
    example_slices: list[str]


class LaunchReliabilityAudit(BaseModel):
    has_automatic_retry: bool
    retry_strategy: str
    notes: list[str]


class LossInventoryAudit(BaseModel):
    recipe_loss_keys: list[str]
    core_loss_modules: list[str]


class TrainingPipelineAuditSnapshot(BaseModel):
    generated_at: str
    supports_multi_policy_training: bool
    cogsguard_train_defaults: CogsguardTrainDefaultsAudit
    multi_policy: MultiPolicySupportAudit
    launch_reliability: LaunchReliabilityAudit
    loss_inventory: LossInventoryAudit
