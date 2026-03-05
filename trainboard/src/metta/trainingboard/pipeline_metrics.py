from __future__ import annotations

import importlib
import math
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import islice
from typing import Optional

from pydantic import BaseModel, Field

from metta.trainingboard.models import (
    LLMTaskScores,
    MeaningfulResultMetrics,
    PipelineFamilyShare,
    ResearchFunnelSnapshot,
    ResearchFunnelStages,
    ResearchPaperRecord,
    SearchCoverageMetrics,
    TrainingExperimentMetrics,
    TrainingPipelineSnapshot,
)

WEEK_WINDOW_DAYS = 7
MONTH_WINDOW_DAYS = 30
STALE_RUNNING_DAYS = 14
ABS_MEANINGFUL_DELTA = 0.02
REL_MEANINGFUL_DELTA = 0.03
MEANINGFUL_COVERAGE_THRESHOLD = 0.25
MEANINGFUL_MIN_SAMPLES = 8

QUALITY_METRIC_KEYS = [
    "sweep/score",
    "env_game/cogs/aligned.junction.held",
    "env_game/clips/aligned.junction.held",
    "env_collective/cogs/aligned.junction.held",
    "env_eval/cogs/aligned.junction.held",
    "env_eval/clips/aligned.junction.held",
]

_PAPER_HOST_PATTERN = re.compile(
    r"(arxiv\.org|openreview\.net|paperswithcode\.com|aclanthology\.org|ieeexplore\.ieee\.org|dl\.acm\.org|nature\.com|science\.org)",
    re.IGNORECASE,
)
_REPO_PATTERN = re.compile(r"github\.com/[^\s)]+", re.IGNORECASE)
_DIGIT_RUN_PATTERN = re.compile(r"\d{8,}")


class WandbRunSample(BaseModel):
    run_id: str
    display_name: str
    state: str
    created_at: datetime
    summary_metrics: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


def fetch_wandb_state_samples(
    *,
    entity: str,
    project: str,
    per_state_limit: int,
    metric_keys: list[str] = QUALITY_METRIC_KEYS,
) -> list[WandbRunSample]:
    wandb = importlib.import_module("wandb")
    api = wandb.Api(timeout=45)
    samples: list[WandbRunSample] = []
    for state in ("running", "finished", "crashed"):
        runs = islice(
            api.runs(f"{entity}/{project}", filters={"state": state}, order="-created_at"),
            max(1, per_state_limit),
        )
        for run in runs:
            created_at = _to_datetime(run.created_at)
            summary_payload = dict(run.summary or {})
            metric_values = {
                metric_key: metric_value
                for metric_key in metric_keys
                if (metric_value := _numeric(summary_payload.get(metric_key))) is not None
            }
            samples.append(
                WandbRunSample(
                    run_id=run.id,
                    display_name=str(getattr(run, "display_name", None) or getattr(run, "name", None) or run.id),
                    state=state,
                    created_at=created_at,
                    summary_metrics=metric_values,
                    tags=[str(tag) for tag in list(getattr(run, "tags", []) or [])],
                )
            )
    return samples


def build_training_pipeline_snapshot_from_samples(
    samples: list[WandbRunSample],
    *,
    now_utc: Optional[datetime] = None,
) -> TrainingPipelineSnapshot:
    now = now_utc or datetime.now(tz=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    month_cutoff = now - timedelta(days=MONTH_WINDOW_DAYS)
    week_cutoff = now - timedelta(days=WEEK_WINDOW_DAYS)
    stale_cutoff = now - timedelta(days=STALE_RUNNING_DAYS)

    running_now = sum(1 for sample in samples if sample.state == "running")
    running_recent_7d = sum(1 for sample in samples if sample.state == "running" and sample.created_at >= week_cutoff)
    running_stale_gt_14d = sum(
        1 for sample in samples if sample.state == "running" and sample.created_at < stale_cutoff
    )
    finished_recent_7d = sum(1 for sample in samples if sample.state == "finished" and sample.created_at >= week_cutoff)
    crashed_recent_7d = sum(1 for sample in samples if sample.state == "crashed" and sample.created_at >= week_cutoff)

    denominator = finished_recent_7d + crashed_recent_7d
    crash_rate = _safe_ratio(crashed_recent_7d, denominator)

    experiments = TrainingExperimentMetrics(
        running_now=running_now,
        running_recent_7d=running_recent_7d,
        running_stale_gt_14d=running_stale_gt_14d,
        finished_recent_7d=finished_recent_7d,
        crashed_recent_7d=crashed_recent_7d,
        starts_recent_7d_lower_bound=running_recent_7d + finished_recent_7d + crashed_recent_7d,
        crash_rate_recent_7d=round(crash_rate, 3),
    )

    family_counts = Counter(_run_family(sample.display_name) for sample in samples if sample.created_at >= month_cutoff)
    family_total = sum(family_counts.values())
    sorted_family_items = family_counts.most_common(10)
    dominant_families = [
        PipelineFamilyShare(family=family, count=count, share=round(_safe_ratio(count, family_total), 3))
        for family, count in sorted_family_items
    ]
    top_share = dominant_families[0].share if dominant_families else 0.0
    search_coverage = SearchCoverageMetrics(
        unique_families_30d=len(family_counts),
        top_family_share_30d=round(top_share, 3),
        family_entropy_30d=round(_normalized_entropy(list(family_counts.values())), 3),
        dominant_families_30d=dominant_families,
    )

    meaningful = _meaningful_results_snapshot(samples=samples, now=now)
    return TrainingPipelineSnapshot(
        generated_at=now.isoformat(),
        available=True,
        source="wandb_state_samples",
        notes=[f"samples={len(samples)} (running/finished/crashed state slices)"],
        experiments=experiments,
        search_coverage=search_coverage,
        meaningful_results=meaningful,
    )


def build_research_funnel_snapshot(
    papers: list[ResearchPaperRecord],
    *,
    llm_scores_by_gid: dict[str, LLMTaskScores],
) -> ResearchFunnelSnapshot:
    status_counts: Counter[str] = Counter()
    paper_signal_tasks = 0
    repo_signal_tasks = 0
    implemented_tasks = 0
    paper_repo_tasks = 0
    paper_repo_implemented_tasks = 0
    llm_scored_tasks = 0

    for paper in papers:
        status_value = _implementation_status(paper)
        status_counts[status_value] += 1
        has_paper_signal = _has_paper_signal(paper)
        has_repo_signal = _has_repo_signal(paper)
        is_implemented = _is_implemented(status_value)
        if paper.gid in llm_scores_by_gid:
            llm_scored_tasks += 1
        if has_paper_signal:
            paper_signal_tasks += 1
        if has_repo_signal:
            repo_signal_tasks += 1
        if is_implemented:
            implemented_tasks += 1
        if has_paper_signal and has_repo_signal:
            paper_repo_tasks += 1
        if has_paper_signal and has_repo_signal and is_implemented:
            paper_repo_implemented_tasks += 1

    stages = ResearchFunnelStages(
        paper_selected=paper_signal_tasks,
        author_repo_found=paper_repo_tasks,
        implemented_in_metta=paper_repo_implemented_tasks,
        paper_to_repo_conversion=round(_safe_ratio(paper_repo_tasks, paper_signal_tasks), 3),
        repo_to_impl_conversion=round(_safe_ratio(paper_repo_implemented_tasks, paper_repo_tasks), 3),
    )
    task_total = len(papers)
    return ResearchFunnelSnapshot(
        generated_at=datetime.now(tz=UTC).isoformat(),
        tasks_total=task_total,
        llm_scored_tasks=llm_scored_tasks,
        llm_coverage=round(_safe_ratio(llm_scored_tasks, task_total), 3) if task_total > 0 else 0.0,
        status_counts=dict(status_counts),
        paper_signal_tasks=paper_signal_tasks,
        repo_signal_tasks=repo_signal_tasks,
        implemented_tasks=implemented_tasks,
        paper_repo_tasks=paper_repo_tasks,
        paper_repo_implemented_tasks=paper_repo_implemented_tasks,
        stages=stages,
    )


def _meaningful_results_snapshot(samples: list[WandbRunSample], now: datetime) -> MeaningfulResultMetrics:
    month_cutoff = now - timedelta(days=MONTH_WINDOW_DAYS)
    week_cutoff = now - timedelta(days=WEEK_WINDOW_DAYS)
    finished_month_samples = [
        sample for sample in samples if sample.state == "finished" and sample.created_at >= month_cutoff
    ]

    metric_presence = {
        metric_key: sum(1 for sample in finished_month_samples if metric_key in sample.summary_metrics)
        for metric_key in QUALITY_METRIC_KEYS
    }
    primary_metric = ""
    best_metric_count = 0
    if metric_presence:
        candidate_metric = max(QUALITY_METRIC_KEYS, key=lambda metric_key: metric_presence[metric_key])
        candidate_count = metric_presence[candidate_metric]
        if candidate_count > 0:
            primary_metric = candidate_metric
            best_metric_count = candidate_count

    coverage = _safe_ratio(best_metric_count, len(finished_month_samples)) if primary_metric else 0.0
    measurable = (
        bool(primary_metric)
        and len(finished_month_samples) >= MEANINGFUL_MIN_SAMPLES
        and coverage >= MEANINGFUL_COVERAGE_THRESHOLD
    )
    meaningful_events_7d = 0
    meaningful_events_30d = 0
    if measurable and primary_metric:
        metric_rows = [
            sample
            for sample in finished_month_samples
            if (value := sample.summary_metrics.get(primary_metric)) is not None and math.isfinite(value)
        ]
        metric_rows.sort(key=lambda sample: sample.created_at)
        best_value = -math.inf
        event_timestamps: list[datetime] = []
        for sample in metric_rows:
            value = sample.summary_metrics[primary_metric]
            if best_value == -math.inf:
                event_timestamps.append(sample.created_at)
                best_value = value
                continue
            required_delta = max(ABS_MEANINGFUL_DELTA, abs(best_value) * REL_MEANINGFUL_DELTA)
            if value >= best_value + required_delta:
                event_timestamps.append(sample.created_at)
                best_value = value
        meaningful_events_30d = len(event_timestamps)
        meaningful_events_7d = sum(1 for timestamp in event_timestamps if timestamp >= week_cutoff)

    weekly_rate = meaningful_events_30d / (MONTH_WINDOW_DAYS / WEEK_WINDOW_DAYS)
    return MeaningfulResultMetrics(
        metric_keys_considered=QUALITY_METRIC_KEYS,
        metric_presence_counts=metric_presence,
        primary_metric=primary_metric,
        primary_metric_coverage_ratio=round(coverage, 3),
        measurable=measurable,
        meaningful_events_7d=meaningful_events_7d,
        meaningful_events_30d=meaningful_events_30d,
        weekly_meaningful_rate=round(weekly_rate, 3),
        threshold_definition=f"new best by max({ABS_MEANINGFUL_DELTA}, {int(REL_MEANINGFUL_DELTA * 100)}% relative)",
    )


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _numeric(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if re.fullmatch(r"-?\d+(\.\d+)?", normalized) is None:
            return None
        return float(normalized)
    return None


def _run_family(name: str) -> str:
    normalized = _DIGIT_RUN_PATTERN.sub("", name.lower())
    for separator in (".", "_", "-"):
        if separator in normalized:
            head = normalized.split(separator, 1)[0]
            return head if head else "unknown"
    chunks = normalized.split()
    return chunks[0] if chunks else "unknown"


def _normalized_entropy(counts: list[int]) -> float:
    if not counts:
        return 0.0
    total = float(sum(counts))
    if total <= 0:
        return 0.0
    shares = [count / total for count in counts if count > 0]
    if len(shares) <= 1:
        return 0.0
    entropy = -sum(share * math.log(share) for share in shares)
    return entropy / math.log(len(shares))


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _implementation_status(paper: ResearchPaperRecord) -> str:
    custom_fields = paper.custom_fields
    return custom_fields.get("Implementation Status") or custom_fields.get("Status") or "Unknown"


def _is_implemented(status_value: str) -> bool:
    return status_value.strip().lower() in {"completed", "complete", "done"}


def _has_repo_signal(paper: ResearchPaperRecord) -> bool:
    text = "\n".join(
        [
            paper.title,
            paper.notes,
            *paper.paper_links,
            *paper.recommendations,
            " ".join(paper.custom_fields.values()),
        ]
    )
    return _REPO_PATTERN.search(text) is not None


def _has_paper_signal(paper: ResearchPaperRecord) -> bool:
    if paper.paper_links:
        return True
    text = "\n".join(
        [
            paper.title,
            paper.notes,
            *paper.recommendations,
            " ".join(paper.custom_fields.values()),
        ]
    )
    return _PAPER_HOST_PATTERN.search(text) is not None
