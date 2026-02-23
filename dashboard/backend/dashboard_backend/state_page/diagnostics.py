"""Dashboard computation logic for policy performance analysis.

Ported from skills/cg.policy-dashboard/generate.py — pure functions only, no I/O.
"""

from __future__ import annotations

import json
import random
import statistics
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dashboard.backend.dashboard_backend.state_page.kpi_math import (
    RESOURCES,
    metric_presence_aliases,
    metric_present,
    metric_value,
    safe_div,
)
from dashboard.backend.dashboard_backend.state_page.kpi_math import (
    action_success_rate as kpi_action_success_rate,
)
from dashboard.backend.dashboard_backend.state_page.kpi_math import (
    action_success_total as kpi_action_success_total,
)
from dashboard.backend.dashboard_backend.state_page.kpi_math import (
    junction_control_rate as kpi_junction_control_rate,
)
from dashboard.backend.dashboard_backend.state_page.kpi_math import (
    move_efficiency as kpi_move_efficiency,
)
from dashboard.backend.dashboard_backend.state_page.kpi_math import (
    noop_rate as kpi_noop_rate,
)
from dashboard.backend.dashboard_backend.state_page.kpi_math import (
    resource_retention as kpi_resource_retention,
)

# === Pydantic Models ===


class DashboardEpisode(BaseModel):
    episode_id: str
    job_id: str
    created_at: str | None = None
    replay_url: str | None = None
    thumbnail_url: str | None = None
    opponent_name: str
    opponent_version: int
    team_composition: str  # "6v2", "4v4", "2v6"
    reward: float
    status: str  # "completed", "failed"
    error_type: str | None = None
    error_message: str | None = None
    error_context: dict[str, Any] = Field(default_factory=dict)
    steps: int = 0
    raw_tags: dict[str, str] = Field(default_factory=dict)
    diagnostic_tags: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class DerivedMetrics(BaseModel):
    # Efficiency KPIs (0-1 scale)
    move_efficiency: float = 0.0
    action_success_rate: float = 0.0
    vibe_change_rate: float = 0.0

    # Resource KPIs
    resource_retention: float = 0.0

    # Vulnerability KPIs
    freeze_vulnerability: float = 0.0

    # Junction KPIs
    junction_control_rate: float = 0.0
    alignment_stability: float = 0.0
    net_alignment_rate: float = 0.0

    # Reward KPIs
    avg_reward: float = 0.0

    # Additional KPIs
    noop_rate: float = 0.0
    resource_efficiency_per_step: float = 0.0
    hearts_to_junction_rate: float = 0.0
    reward_consistency: float = 0.0
    reward_nonzero_pct: float = 0.0

    # Strategy profile scores (0-100)
    profile_aggressive: float = 0.0
    profile_defensive: float = 0.0
    profile_resource_hoarder: float = 0.0
    profile_junction_hunter: float = 0.0
    profile_mobile_scout: float = 0.0

    # Diagnostic flags
    diagnostics: list[str] = Field(default_factory=list)


class OpponentStats(BaseModel):
    count: int
    total_reward: float
    avg_reward: float
    avg_metrics: dict[str, float]
    strategy_profile: dict[str, float]


class TeamCompStats(BaseModel):
    composition: str
    count: int
    avg_reward: float
    avg_move_efficiency: float
    avg_junction_aligned: float
    avg_resource_gained: float


class PolicyInfo(BaseModel):
    id: str
    name: str
    version: int
    rank: int | None = None
    score: float | None = None
    matches: int = 0


class OutcomeSnapshot(BaseModel):
    id: str
    name: str
    version: int
    rank: int | None = None
    score: float | None = None
    matches: int = 0
    season: str


class OutcomeDelta(BaseModel):
    rank_delta: int | None = None
    score_delta: float | None = None
    matches_delta: int | None = None


class OutcomeSummary(BaseModel):
    verdict: str = "inconclusive"  # helped | hurt | inconclusive
    reason: str = "No baseline available for comparison."
    evidence_sufficient: bool = False
    current: OutcomeSnapshot
    baseline: OutcomeSnapshot | None = None
    delta: OutcomeDelta = Field(default_factory=OutcomeDelta)


class FailureSummary(BaseModel):
    total_episodes: int = 0
    completed_episodes: int = 0
    failed_episodes: int = 0
    failed_rate: float = 0.0
    timeout_failures: int = 0
    oom_failures: int = 0
    crash_failures: int = 0
    other_failures: int = 0
    freeze_heavy_completed: int = 0
    noop_heavy_completed: int = 0


class CrashDumpSignature(BaseModel):
    signature: str
    count: int = 0
    error_type: str = "unknown"
    example_message: str | None = None


class CrashDumpEntry(BaseModel):
    episode_id: str
    job_id: str
    created_at: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    analysis_command: str
    replay_url: str | None = None


class CrashDumpSummary(BaseModel):
    evidence_sufficient: bool = False
    headline: str = "No failed jobs detected in sampled episodes."
    total_failed: int = 0
    signatures: list[CrashDumpSignature] = Field(default_factory=list)
    entries: list[CrashDumpEntry] = Field(default_factory=list)


class ActionSummary(BaseModel):
    rollout_recommendation: str = "hold"  # block | hold | proceed_cautiously
    headline: str = "Collect more evidence before making rollout decisions."
    actions: list[str] = Field(default_factory=list)


class MatchupSlice(BaseModel):
    key: str
    count: int
    avg_reward: float
    delta_vs_policy: float
    baseline_count: int | None = None
    baseline_avg_reward: float | None = None
    delta_vs_baseline: float | None = None


class MatchupSummary(BaseModel):
    evidence_sufficient: bool = False
    interaction_specific_issue: bool = False
    reason: str = "Insufficient matchup evidence. Collect more episodes."
    current_avg_reward: float = 0.0
    baseline_avg_reward: float | None = None
    global_reward_delta: float | None = None
    opponent_spread: float = 0.0
    best_opponent: str | None = None
    worst_opponent: str | None = None
    composition_spread: float = 0.0
    best_composition: str | None = None
    worst_composition: str | None = None
    opponent_slices: list[MatchupSlice] = Field(default_factory=list)
    composition_slices: list[MatchupSlice] = Field(default_factory=list)


class UnsupportedIssue(BaseModel):
    code: str
    severity: str  # info | warn | error
    message: str
    affected_count: int = 0
    total_count: int = 0
    recommended_action: str


class UnsupportedStateSummary(BaseModel):
    has_unsupported_state: bool = False
    issues: list[UnsupportedIssue] = Field(default_factory=list)


class InstrumentationCheck(BaseModel):
    key: str
    kind: str  # metric | tag | field
    required: bool = True
    present_count: int = 0
    total_count: int = 0
    coverage: float = 0.0
    status: str = "missing"  # pass | partial | missing
    message: str = ""


class InstrumentationValidationSummary(BaseModel):
    template_version: str = "state-page-instrumentation-v1"
    min_coverage_threshold: float = 0.9
    compliant: bool = False
    score: float = 0.0
    checks: list[InstrumentationCheck] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class StatsInventoryField(BaseModel):
    key: str
    kind: str  # metric | tag
    present_count: int = 0
    total_count: int = 0
    coverage: float = 0.0


class StatsInventorySummary(BaseModel):
    total_episodes: int = 0
    completed_episodes: int = 0
    failed_episodes: int = 0
    distinct_metric_keys: int = 0
    distinct_tag_keys: int = 0
    top_metric_keys: list[StatsInventoryField] = Field(default_factory=list)
    top_tag_keys: list[StatsInventoryField] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class VersionTrendPoint(BaseModel):
    id: str
    name: str
    version: int
    rank: int | None = None
    score: float | None = None
    matches: int = 0
    has_leaderboard_data: bool = False


class VersionTrendSummary(BaseModel):
    evidence_sufficient: bool = False
    direction: str = "insufficient"  # improving | declining | mixed | insufficient
    reason: str = "Insufficient leaderboard points for trend inference."
    score_delta_from_oldest: float | None = None
    rank_delta_from_oldest: int | None = None
    points: list[VersionTrendPoint] = Field(default_factory=list)


class TrendExplorerSeries(BaseModel):
    key: str
    label: str
    higher_is_better: bool
    direction: str = "insufficient"  # improving | declining | mixed | insufficient
    reason: str = "Insufficient points for trend inference."
    values: list[float | None] = Field(default_factory=list)
    deltas: list[float | None] = Field(default_factory=list)


class TrendDistribution(BaseModel):
    count: int = 0
    mean: float | None = None
    median: float | None = None
    p10: float | None = None
    p90: float | None = None


class TrendMetricOverlay(BaseModel):
    key: str
    label: str
    higher_is_better: bool
    current_value: float | None = None
    current_display: str = "-"
    team: TrendDistribution = Field(default_factory=TrendDistribution)
    population: TrendDistribution = Field(default_factory=TrendDistribution)
    delta_vs_team_mean: float | None = None
    delta_vs_population_mean: float | None = None
    signal: str = "insufficient"  # outperforming | underperforming | mixed | insufficient
    reason: str = "Insufficient team/population overlay context."


class SubmissionPatternGroup(BaseModel):
    code: str
    title: str
    metric_key: str
    severity: str  # info | warn | high
    count: int = 0
    versions: list[str] = Field(default_factory=list)
    evidence: str
    next_action: str


class TrendExplorerSummary(BaseModel):
    evidence_sufficient: bool = False
    selected_metric: str = "score"
    version_labels: list[str] = Field(default_factory=list)
    series: list[TrendExplorerSeries] = Field(default_factory=list)
    metric_overlays: list[TrendMetricOverlay] = Field(default_factory=list)
    submission_patterns: list[SubmissionPatternGroup] = Field(default_factory=list)


class ConfidenceInterval(BaseModel):
    key: str
    label: str
    point_estimate: float | None = None
    lower: float | None = None
    upper: float | None = None
    crosses_zero: bool | None = None
    current_samples: int = 0
    baseline_samples: int = 0
    interpretation: str = "Insufficient data to estimate confidence interval."


class ConfidenceSummary(BaseModel):
    evidence_sufficient: bool = False
    intervals: list[ConfidenceInterval] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class OrchestrationExperimentHook(BaseModel):
    id: str
    priority: int = 1
    title: str
    objective: str
    rationale: str
    actions: list[str] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)


class OrchestrationPayloadTemplate(BaseModel):
    template_version: str = "state-page-orchestration-v1"
    policy_version_id: str = ""
    rollout_gate: str = "hold"
    mode: str = "collect_more_evidence"
    experiment_ids: list[str] = Field(default_factory=list)


class OrchestrationHookSummary(BaseModel):
    evidence_sufficient: bool = False
    mode: str = "collect_more_evidence"  # ready | collect_more_evidence
    headline: str = "Collect additional evidence before orchestrating expensive experiments."
    experiments: list[OrchestrationExperimentHook] = Field(default_factory=list)
    payload_template: OrchestrationPayloadTemplate = Field(default_factory=OrchestrationPayloadTemplate)


class PatternSignal(BaseModel):
    code: str
    title: str
    severity: str  # info | warn | high
    confidence: str  # low | medium | high
    evidence: str
    next_action: str


class PatternExtractionSummary(BaseModel):
    evidence_sufficient: bool = False
    headline: str = "Collect more evidence before extracting strong patterns."
    signals: list[PatternSignal] = Field(default_factory=list)


class DashboardDerived(BaseModel):
    kpis: DerivedMetrics
    team_comp: list[TeamCompStats]
    opponent_metrics: dict[str, OpponentStats]
    outcome: OutcomeSummary | None = None
    failures: FailureSummary
    unsupported: UnsupportedStateSummary | None = None
    instrumentation: InstrumentationValidationSummary | None = None
    stats_inventory: StatsInventorySummary | None = None
    actions: ActionSummary | None = None
    crash_dump: CrashDumpSummary | None = None
    matchup: MatchupSummary | None = None
    confidence: ConfidenceSummary | None = None
    orchestration: OrchestrationHookSummary | None = None
    trend: VersionTrendSummary | None = None
    trend_explorer: TrendExplorerSummary | None = None
    patterns: PatternExtractionSummary | None = None


class EpisodeSelectionMetadata(BaseModel):
    limit: int
    offset: int = 0
    ordering: str = "created_at_desc"
    sampled_episode_count: int = 0
    includes_failed_jobs_without_episode: bool = True
    baseline_limit: int | None = None


class DashboardResponse(BaseModel):
    policy: PolicyInfo
    episodes: list[DashboardEpisode]
    season: str
    generated_at: str
    selection: EpisodeSelectionMetadata
    derived: DashboardDerived


# === Pure computation functions ===


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    weight = idx - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * weight


def _compute_distribution(values: list[float]) -> TrendDistribution:
    if not values:
        return TrendDistribution(count=0)
    return TrendDistribution(
        count=len(values),
        mean=round(statistics.mean(values), 6),
        median=round(statistics.median(values), 6),
        p10=round(_percentile(values, 0.1), 6),
        p90=round(_percentile(values, 0.9), 6),
    )


def compute_episode_diagnostic_tags(episode: DashboardEpisode) -> list[str]:
    tags: list[str] = []
    metrics = episode.metrics

    if episode.status == "failed":
        tags.append("failed")
        if episode.error_type:
            lowered = episode.error_type.lower()
            if "timeout" in lowered:
                tags.append("timeout")
            elif "oom" in lowered:
                tags.append("oom")
            elif "crash" in lowered or "error" in lowered or "exception" in lowered:
                tags.append("crash")
        return tags

    aligned = metric_value(metrics, "junction.aligned_by_agent")
    scrambled = metric_value(metrics, "junction.scrambled_by_agent")
    mined = sum(float(metrics.get(f"{resource}.gained", 0)) for resource in RESOURCES)
    noop = float(metrics.get("action.noop.success", 0))
    total_action_success = sum(
        float(value)
        for key, value in metrics.items()
        if key.startswith("action.") and key.endswith(".success") and isinstance(value, (int, float))
    )
    action_failed = float(metrics.get("action.failed", 0))
    total_actions = total_action_success + action_failed
    noop_rate = safe_div(noop, total_actions)

    tags.append(f"did_align={'true' if aligned > 0 else 'false'}")
    tags.append(f"did_mine={'true' if mined > 0 else 'false'}")
    tags.append(f"did_scramble={'true' if scrambled > 0 else 'false'}")
    tags.append(f"stalled_noop_heavy={'true' if noop_rate >= 0.4 else 'false'}")

    aggression_signal = scrambled + float(metrics.get("action.change_vibe.success", 0))
    if aggression_signal >= 8:
        aggression_bucket = "large"
    elif aggression_signal >= 3:
        aggression_bucket = "medium"
    else:
        aggression_bucket = "small"
    tags.append(f"aggression_bucket={aggression_bucket}")

    if episode.reward < 0.5:
        tags.append("reward_tier=low")
    elif episode.reward > 2.0:
        tags.append("reward_tier=high")
    else:
        tags.append("reward_tier=mid")

    return tags


def compute_unsupported_state(episodes: list[DashboardEpisode]) -> UnsupportedStateSummary:
    issues: list[UnsupportedIssue] = []

    if not episodes:
        return UnsupportedStateSummary(
            has_unsupported_state=True,
            issues=[
                UnsupportedIssue(
                    code="no_episodes",
                    severity="error",
                    message="No episodes available for this policy version.",
                    affected_count=0,
                    total_count=0,
                    recommended_action="Run or fetch evaluation episodes before using this diagnosis page.",
                )
            ],
        )

    total = len(episodes)
    completed = [episode for episode in episodes if episode.status == "completed"]

    if not completed:
        issues.append(
            UnsupportedIssue(
                code="no_completed_episodes",
                severity="error",
                message="All sampled episodes failed; behavioral diagnosis is unavailable.",
                affected_count=total,
                total_count=total,
                recommended_action=(
                    "Fix runtime reliability first, then rerun evaluation to collect completed episodes."
                ),
            )
        )
        return UnsupportedStateSummary(has_unsupported_state=True, issues=issues)

    unknown_team_comp = sum(1 for episode in completed if episode.team_composition == "?v?")
    if unknown_team_comp > 0:
        issues.append(
            UnsupportedIssue(
                code="missing_team_composition_tags",
                severity="warn",
                message="Some episodes are missing assignment tags, so team-composition analysis is partial.",
                affected_count=unknown_team_comp,
                total_count=len(completed),
                recommended_action="Ensure episode tags include assignments and policy_version_ids for all runs.",
            )
        )

    missing_replay_url = sum(1 for episode in completed if not episode.replay_url)
    if missing_replay_url > 0:
        issues.append(
            UnsupportedIssue(
                code="missing_replay_urls",
                severity="warn",
                message="Some completed episodes have no replay URL, limiting drill-down validation.",
                affected_count=missing_replay_url,
                total_count=len(completed),
                recommended_action="Enable replay artifact upload/preservation for evaluation jobs.",
            )
        )

    required_metric_keys = [
        "action.move.success",
        "action.move.failed",
        "junction.aligned_by_agent",
        "junction.scrambled_by_agent",
    ]
    for metric_key in required_metric_keys:
        aliases = metric_presence_aliases(metric_key)
        missing_metric = sum(1 for episode in completed if not metric_present(episode.metrics, metric_key))
        if missing_metric > 0:
            alias_note = ""
            if len(aliases) > 1:
                alias_note = f" (aliases: {', '.join(f'`{alias}`' for alias in aliases[1:])})"
            issues.append(
                UnsupportedIssue(
                    code=f"missing_metric::{metric_key}",
                    severity="warn",
                    message=f"Metric `{metric_key}`{alias_note} is missing in part of the sample.",
                    affected_count=missing_metric,
                    total_count=len(completed),
                    recommended_action=(
                        "Update instrumentation template to emit required core metrics for all episodes."
                    ),
                )
            )

    return UnsupportedStateSummary(has_unsupported_state=len(issues) > 0, issues=issues)


def compute_instrumentation_validation(
    episodes: list[DashboardEpisode],
    min_coverage_threshold: float = 0.9,
) -> InstrumentationValidationSummary:
    completed = [episode for episode in episodes if episode.status == "completed"]
    completed_total = len(completed)
    all_total = len(episodes)

    checks: list[InstrumentationCheck] = []

    def coverage_status(coverage: float) -> str:
        if coverage >= min_coverage_threshold:
            return "pass"
        if coverage > 0:
            return "partial"
        return "missing"

    def append_check(key: str, kind: str, present: int, total: int, message: str) -> None:
        coverage = safe_div(present, total)
        checks.append(
            InstrumentationCheck(
                key=key,
                kind=kind,
                present_count=present,
                total_count=total,
                coverage=coverage,
                status=coverage_status(coverage) if total > 0 else "missing",
                message=message,
            )
        )

    def add_metric_check(metric_key: str) -> None:
        aliases = metric_presence_aliases(metric_key)
        present = sum(1 for episode in completed if metric_present(episode.metrics, metric_key))
        alias_note = ""
        if len(aliases) > 1:
            alias_note = f" (aliases: {', '.join(f'`{alias}`' for alias in aliases[1:])})"
        append_check(
            metric_key,
            "metric",
            present,
            completed_total,
            f"Metric `{metric_key}`{alias_note} coverage across completed episodes.",
        )

    def add_tag_check(tag_key: str) -> None:
        present = sum(1 for episode in completed if episode.raw_tags.get(tag_key))
        append_check(
            tag_key,
            "tag",
            present,
            completed_total,
            f"Tag `{tag_key}` coverage across completed episodes.",
        )

    def add_field_check(field_key: str) -> None:
        field_getters = {
            "created_at": lambda episode: episode.created_at,
            "replay_url": lambda episode: episode.replay_url,
        }
        assert field_key in field_getters, f"Unsupported field check: {field_key}"

        target_episodes = completed if field_key == "replay_url" else episodes
        total = completed_total if field_key == "replay_url" else all_total
        present = sum(1 for episode in target_episodes if field_getters[field_key](episode))
        append_check(
            field_key,
            "field",
            present,
            total,
            f"Field `{field_key}` coverage in sampled episodes.",
        )

    required_metrics = [
        "action.move.success",
        "action.move.failed",
        "action.noop.success",
        "junction.aligned_by_agent",
        "junction.scrambled_by_agent",
        "status.frozen.ticks",
        "heart.gained",
    ]
    for key in required_metrics:
        add_metric_check(key)

    required_tags = [
        "assignments",
        "policy_version_ids",
    ]
    for key in required_tags:
        add_tag_check(key)

    required_fields = [
        "created_at",
        "replay_url",
    ]
    for key in required_fields:
        add_field_check(key)

    coverage_values = [check.coverage for check in checks]
    score = statistics.mean(coverage_values) if coverage_values else 0.0
    compliant = all(check.status == "pass" for check in checks) and completed_total > 0

    actions: list[str] = []
    missing_or_partial = [check for check in checks if check.status != "pass"]
    if missing_or_partial:
        actions.append("Adopt a shared State Page instrumentation template/contract and rerun evaluation.")
        for check in missing_or_partial[:4]:
            actions.append(
                f"Improve {check.kind} `{check.key}` coverage from "
                f"{check.present_count}/{check.total_count} to >= {int(min_coverage_threshold * 100)}%."
            )
    else:
        actions.append("Instrumentation coverage meets the minimum State Page contract.")

    return InstrumentationValidationSummary(
        min_coverage_threshold=min_coverage_threshold,
        compliant=compliant,
        score=round(score, 4),
        checks=checks,
        recommended_actions=actions,
    )


def compute_version_trend_summary(
    policy_versions: list[PolicyInfo],
    min_points_for_inference: int = 3,
) -> VersionTrendSummary:
    if not policy_versions:
        return VersionTrendSummary()

    points = [
        VersionTrendPoint(
            id=policy.id,
            name=policy.name,
            version=policy.version,
            rank=policy.rank,
            score=policy.score,
            matches=policy.matches,
            has_leaderboard_data=(policy.rank is not None or policy.score is not None),
        )
        for policy in sorted(policy_versions, key=lambda policy: policy.version)
    ]
    leaderboard_points = [point for point in points if point.has_leaderboard_data]

    if len(leaderboard_points) < min_points_for_inference:
        return VersionTrendSummary(
            evidence_sufficient=False,
            direction="insufficient",
            reason=(
                "Insufficient recent versions with leaderboard coverage. "
                "Submit/evaluate more consecutive versions for trend inference."
            ),
            points=points,
        )

    oldest = leaderboard_points[0]
    newest = leaderboard_points[-1]
    score_delta = None
    rank_delta = None
    if oldest.score is not None and newest.score is not None:
        score_delta = round(newest.score - oldest.score, 6)
    if oldest.rank is not None and newest.rank is not None:
        rank_delta = newest.rank - oldest.rank

    if score_delta is not None:
        if score_delta >= 0.03:
            direction = "improving"
            reason = (
                f"Recent policy lineage is improving (+{score_delta:.3f} score from "
                f"v{oldest.version} to v{newest.version})."
            )
        elif score_delta <= -0.03:
            direction = "declining"
            reason = (
                f"Recent policy lineage is declining ({score_delta:.3f} score from "
                f"v{oldest.version} to v{newest.version})."
            )
        else:
            direction = "mixed"
            reason = (
                f"Recent score movement is near-flat ({score_delta:+.3f}) from v{oldest.version} to v{newest.version}."
            )
    elif rank_delta is not None:
        if rank_delta <= -2:
            direction = "improving"
            reason = (
                f"Recent rank trend is improving ({abs(rank_delta)} places) from "
                f"v{oldest.version} to v{newest.version}."
            )
        elif rank_delta >= 2:
            direction = "declining"
            reason = (
                f"Recent rank trend is declining ({rank_delta} places) from v{oldest.version} to v{newest.version}."
            )
        else:
            direction = "mixed"
            reason = f"Recent rank movement is small ({rank_delta:+d}) from v{oldest.version} to v{newest.version}."
    else:
        direction = "insufficient"
        reason = "Recent versions do not have comparable score/rank fields."

    return VersionTrendSummary(
        evidence_sufficient=direction != "insufficient",
        direction=direction,
        reason=reason,
        score_delta_from_oldest=score_delta,
        rank_delta_from_oldest=rank_delta,
        points=points,
    )


def compute_trend_explorer_summary(
    policy_versions: list[PolicyInfo],
    population_versions: list[PolicyInfo] | None = None,
    min_points_for_inference: int = 3,
) -> TrendExplorerSummary:
    if not policy_versions:
        return TrendExplorerSummary(
            evidence_sufficient=False,
            selected_metric="score",
            version_labels=[],
            series=[],
            metric_overlays=[],
            submission_patterns=[],
        )

    points = sorted(policy_versions, key=lambda policy: policy.version)
    version_labels = [f"v{point.version}" for point in points]

    def infer_direction(
        values: list[float | None],
        higher_is_better: bool,
        threshold: float,
    ) -> tuple[str, str]:
        valid = [value for value in values if value is not None]
        if len(valid) < min_points_for_inference:
            return (
                "insufficient",
                "Insufficient comparable points for this metric.",
            )
        first = valid[0]
        last = valid[-1]
        delta = last - first
        if abs(delta) < threshold:
            return (
                "mixed",
                f"Metric movement is near-flat ({delta:+.3f}) over recent versions.",
            )
        improving = delta > 0 if higher_is_better else delta < 0
        if improving:
            return (
                "improving",
                f"Metric trend is improving ({delta:+.3f}) over recent versions.",
            )
        return (
            "declining",
            f"Metric trend is declining ({delta:+.3f}) over recent versions.",
        )

    score_values: list[float | None] = [point.score for point in points]
    rank_values: list[float | None] = [float(point.rank) if point.rank is not None else None for point in points]
    match_values: list[float | None] = [float(point.matches) for point in points]

    def deltas(values: list[float | None]) -> list[float | None]:
        result: list[float | None] = []
        previous: float | None = None
        for value in values:
            if value is None or previous is None:
                result.append(None)
            else:
                result.append(round(value - previous, 6))
            previous = value
        return result

    score_direction, score_reason = infer_direction(score_values, higher_is_better=True, threshold=0.03)
    rank_direction, rank_reason = infer_direction(rank_values, higher_is_better=False, threshold=1.0)
    match_direction, match_reason = infer_direction(match_values, higher_is_better=True, threshold=1.0)

    series = [
        TrendExplorerSeries(
            key="score",
            label="Leaderboard Score",
            higher_is_better=True,
            direction=score_direction,
            reason=score_reason,
            values=score_values,
            deltas=deltas(score_values),
        ),
        TrendExplorerSeries(
            key="rank",
            label="Leaderboard Rank",
            higher_is_better=False,
            direction=rank_direction,
            reason=rank_reason,
            values=rank_values,
            deltas=deltas(rank_values),
        ),
        TrendExplorerSeries(
            key="matches",
            label="Match Count",
            higher_is_better=True,
            direction=match_direction,
            reason=match_reason,
            values=match_values,
            deltas=deltas(match_values),
        ),
    ]

    score_has_enough = len([value for value in score_values if value is not None]) >= min_points_for_inference
    rank_has_enough = len([value for value in rank_values if value is not None]) >= min_points_for_inference
    selected_metric = "score" if score_has_enough else ("rank" if rank_has_enough else "matches")

    population = population_versions or []
    population_score_values = [p.score for p in population if p.score is not None]
    population_rank_values = [float(p.rank) for p in population if p.rank is not None]
    population_match_values = [float(p.matches) for p in population]

    def overlay_signal(
        current_value: float | None,
        team_mean: float | None,
        population_mean: float | None,
        higher_is_better: bool,
    ) -> tuple[str, str]:
        if current_value is None or team_mean is None or population_mean is None:
            return ("insufficient", "Insufficient team/population overlay context for this metric.")
        better_vs_team = current_value > team_mean if higher_is_better else current_value < team_mean
        better_vs_population = current_value > population_mean if higher_is_better else current_value < population_mean
        if better_vs_team and better_vs_population:
            return ("outperforming", "Current metric is better than both team and population means.")
        if not better_vs_team and not better_vs_population:
            return ("underperforming", "Current metric is below both team and population means.")
        return ("mixed", "Current metric is above one reference cohort and below the other.")

    def format_metric_value(metric_key: str, value: float | None) -> str:
        if value is None:
            return "-"
        if metric_key == "rank":
            return f"#{int(round(value))}"
        return f"{value:.3f}"

    metric_overlays: list[TrendMetricOverlay] = []
    for metric_series in series:
        values = metric_series.values
        current_value = values[-1] if values else None
        team_reference_values = [value for value in values[:-1] if value is not None]
        if len(team_reference_values) < 2:
            team_reference_values = [value for value in values if value is not None]

        if metric_series.key == "score":
            population_reference_values = population_score_values
        elif metric_series.key == "rank":
            population_reference_values = population_rank_values
        else:
            population_reference_values = population_match_values

        team_distribution = _compute_distribution(team_reference_values)
        population_distribution = _compute_distribution(population_reference_values)
        signal, reason = overlay_signal(
            current_value=current_value,
            team_mean=team_distribution.mean,
            population_mean=population_distribution.mean,
            higher_is_better=metric_series.higher_is_better,
        )
        delta_vs_team = (
            round(current_value - team_distribution.mean, 6)
            if current_value is not None and team_distribution.mean is not None
            else None
        )
        delta_vs_population = (
            round(current_value - population_distribution.mean, 6)
            if current_value is not None and population_distribution.mean is not None
            else None
        )
        metric_overlays.append(
            TrendMetricOverlay(
                key=metric_series.key,
                label=metric_series.label,
                higher_is_better=metric_series.higher_is_better,
                current_value=current_value,
                current_display=format_metric_value(metric_series.key, current_value),
                team=team_distribution,
                population=population_distribution,
                delta_vs_team_mean=delta_vs_team,
                delta_vs_population_mean=delta_vs_population,
                signal=signal,
                reason=reason,
            )
        )

    selected_series = next((metric_series for metric_series in series if metric_series.key == selected_metric), None)
    submission_patterns: list[SubmissionPatternGroup] = []
    if selected_series is not None:
        threshold_by_metric = {"score": 0.03, "rank": 1.0, "matches": 1.0}
        threshold = threshold_by_metric.get(selected_series.key, 0.03)
        transitions: list[dict[str, Any]] = []
        for idx in range(1, len(selected_series.deltas)):
            delta = selected_series.deltas[idx]
            if delta is None:
                continue
            if abs(delta) < threshold:
                bucket = "flat"
            else:
                improving = delta > 0 if selected_series.higher_is_better else delta < 0
                bucket = "improvement" if improving else "regression"
            transitions.append(
                {
                    "bucket": bucket,
                    "delta": delta,
                    "transition": f"{version_labels[idx - 1]}->{version_labels[idx]}",
                }
            )

        if transitions:
            grouped: list[dict[str, Any]] = []
            current_group: dict[str, Any] = {"bucket": transitions[0]["bucket"], "deltas": [], "versions": []}
            for transition in transitions:
                if transition["bucket"] != current_group["bucket"]:
                    grouped.append(current_group)
                    current_group = {"bucket": transition["bucket"], "deltas": [], "versions": []}
                current_group["deltas"].append(float(transition["delta"]))
                current_group["versions"].append(str(transition["transition"]))
            grouped.append(current_group)

            for group in grouped:
                bucket = group["bucket"]
                count = len(group["deltas"])
                avg_delta = statistics.mean(group["deltas"])
                if bucket == "regression":
                    code = "regression_run"
                    title = "Regression cluster across submissions"
                    severity = "high"
                    next_action = (
                        "Compare this transition cluster against last stable submission and isolate the shared change."
                    )
                elif bucket == "improvement":
                    code = "improvement_run"
                    title = "Improvement cluster across submissions"
                    severity = "info"
                    next_action = (
                        "Preserve the shared ingredients in this run and regression-test reliability before rollout."
                    )
                else:
                    code = "flat_run"
                    title = "Near-flat submission cluster"
                    severity = "warn"
                    next_action = (
                        "Increase experiment contrast or sample size; current submission deltas are mostly noise."
                    )
                submission_patterns.append(
                    SubmissionPatternGroup(
                        code=code,
                        title=title,
                        metric_key=selected_series.key,
                        severity=severity,
                        count=count,
                        versions=group["versions"],
                        evidence=(
                            f"{count} consecutive {selected_series.key} transition(s), avg delta {avg_delta:+.3f}."
                        ),
                        next_action=next_action,
                    )
                )

            severity_rank = {"high": 0, "warn": 1, "info": 2}
            submission_patterns.sort(key=lambda group: (severity_rank.get(group.severity, 3), -group.count))

    evidence_sufficient = any(metric.direction != "insufficient" for metric in series)
    return TrendExplorerSummary(
        evidence_sufficient=evidence_sufficient,
        selected_metric=selected_metric,
        version_labels=version_labels,
        series=series,
        metric_overlays=metric_overlays,
        submission_patterns=submission_patterns,
    )


def _bootstrap_mean_delta_interval(
    current_values: list[float],
    baseline_values: list[float],
    sample_count: int,
    seed: int,
) -> tuple[float, float, float]:
    rng = random.Random(seed)
    current_n = len(current_values)
    baseline_n = len(baseline_values)
    deltas: list[float] = []

    for _ in range(sample_count):
        sampled_current = [current_values[rng.randrange(current_n)] for _ in range(current_n)]
        sampled_baseline = [baseline_values[rng.randrange(baseline_n)] for _ in range(baseline_n)]
        deltas.append(statistics.mean(sampled_current) - statistics.mean(sampled_baseline))

    point_estimate = statistics.mean(current_values) - statistics.mean(baseline_values)
    lower = _percentile(deltas, 0.05)
    upper = _percentile(deltas, 0.95)
    return (point_estimate, lower, upper)


def compute_confidence_summary(
    current_episodes: list[DashboardEpisode],
    baseline_episodes: list[DashboardEpisode],
    min_samples: int = 5,
    bootstrap_samples: int = 300,
) -> ConfidenceSummary:
    intervals: list[ConfidenceInterval] = []

    current_completed_rewards = [episode.reward for episode in current_episodes if episode.status == "completed"]
    baseline_completed_rewards = [episode.reward for episode in baseline_episodes if episode.status == "completed"]
    if len(current_completed_rewards) >= min_samples and len(baseline_completed_rewards) >= min_samples:
        reward_delta, reward_lower, reward_upper = _bootstrap_mean_delta_interval(
            current_completed_rewards,
            baseline_completed_rewards,
            sample_count=bootstrap_samples,
            seed=17,
        )
        reward_crosses_zero = reward_lower <= 0 <= reward_upper
        intervals.append(
            ConfidenceInterval(
                key="reward_delta",
                label="Average reward delta",
                point_estimate=round(reward_delta, 6),
                lower=round(reward_lower, 6),
                upper=round(reward_upper, 6),
                crosses_zero=reward_crosses_zero,
                current_samples=len(current_completed_rewards),
                baseline_samples=len(baseline_completed_rewards),
                interpretation=(
                    "Reward delta confidence interval crosses zero; collect more reward evidence."
                    if reward_crosses_zero
                    else "Reward delta direction is consistent in bootstrap samples."
                ),
            )
        )
    else:
        intervals.append(
            ConfidenceInterval(
                key="reward_delta",
                label="Average reward delta",
                current_samples=len(current_completed_rewards),
                baseline_samples=len(baseline_completed_rewards),
                interpretation=(f"Need >= {min_samples} completed episodes in both current and baseline samples."),
            )
        )

    current_failure_values = [1.0 if episode.status == "failed" else 0.0 for episode in current_episodes]
    baseline_failure_values = [1.0 if episode.status == "failed" else 0.0 for episode in baseline_episodes]
    if len(current_failure_values) >= min_samples and len(baseline_failure_values) >= min_samples:
        failure_delta, failure_lower, failure_upper = _bootstrap_mean_delta_interval(
            current_failure_values,
            baseline_failure_values,
            sample_count=bootstrap_samples,
            seed=23,
        )
        failure_crosses_zero = failure_lower <= 0 <= failure_upper
        intervals.append(
            ConfidenceInterval(
                key="failure_rate_delta",
                label="Failure-rate delta",
                point_estimate=round(failure_delta, 6),
                lower=round(failure_lower, 6),
                upper=round(failure_upper, 6),
                crosses_zero=failure_crosses_zero,
                current_samples=len(current_failure_values),
                baseline_samples=len(baseline_failure_values),
                interpretation=(
                    "Failure-rate interval crosses zero; reliability direction is inconclusive."
                    if failure_crosses_zero
                    else "Failure-rate delta direction is consistent in bootstrap samples."
                ),
            )
        )
    else:
        intervals.append(
            ConfidenceInterval(
                key="failure_rate_delta",
                label="Failure-rate delta",
                current_samples=len(current_failure_values),
                baseline_samples=len(baseline_failure_values),
                interpretation=(f"Need >= {min_samples} episodes in both current and baseline samples."),
            )
        )

    evidence_sufficient = any(interval.crosses_zero is False for interval in intervals)
    recommended_actions: list[str] = []
    if evidence_sufficient:
        recommended_actions.append("Use confidence-consistent deltas to prioritize the next patch experiment.")
    else:
        recommended_actions.append(
            "Collect more matched baseline/current episodes before making strong rollout prescriptions."
        )
    for interval in intervals:
        if interval.crosses_zero:
            recommended_actions.append(
                f"`{interval.label}` is inconclusive; increase sample size or reduce matchup variance."
            )

    return ConfidenceSummary(
        evidence_sufficient=evidence_sufficient,
        intervals=intervals,
        recommended_actions=recommended_actions,
    )


def compute_pattern_extraction_summary(
    outcome: OutcomeSummary,
    failures: FailureSummary,
    matchup: MatchupSummary,
    instrumentation: InstrumentationValidationSummary,
    trend_explorer: TrendExplorerSummary,
    unsupported: UnsupportedStateSummary,
) -> PatternExtractionSummary:
    signals: list[PatternSignal] = []

    if failures.failed_rate >= 0.1 or failures.timeout_failures > 0 or failures.oom_failures > 0:
        signals.append(
            PatternSignal(
                code="reliability_risk",
                title="Reliability regression risk",
                severity="high",
                confidence="high",
                evidence=(
                    f"Failed rate {failures.failed_rate * 100:.1f}% with "
                    f"timeouts={failures.timeout_failures}, oom={failures.oom_failures}."
                ),
                next_action="Prioritize timeout/OOM root-cause and rerun the same eval slice before rollout.",
            )
        )

    if matchup.interaction_specific_issue:
        signals.append(
            PatternSignal(
                code="interaction_specific_regression",
                title="Interaction-specific regression",
                severity="warn",
                confidence="medium",
                evidence=matchup.reason,
                next_action="Focus on worst matchup/composition slices before global policy changes.",
            )
        )
    elif outcome.verdict == "hurt":
        signals.append(
            PatternSignal(
                code="global_regression",
                title="Global regression pattern",
                severity="high",
                confidence="medium" if outcome.evidence_sufficient else "low",
                evidence=outcome.reason,
                next_action="Target the dominant global driver (junction/noop/freeze) and compare against baseline.",
            )
        )

    if not instrumentation.compliant:
        missing = sum(1 for check in instrumentation.checks if check.status != "pass")
        signals.append(
            PatternSignal(
                code="instrumentation_gap",
                title="Instrumentation contract gaps",
                severity="warn",
                confidence="high",
                evidence=f"{missing} required instrumentation checks are partial/missing.",
                next_action="Adopt template v1 and fix required metrics/tags/fields before high-confidence diagnosis.",
            )
        )

    score_series = next(
        (series for series in trend_explorer.series if series.key == trend_explorer.selected_metric),
        None,
    )
    if score_series and score_series.direction == "declining":
        signals.append(
            PatternSignal(
                code="trend_decline",
                title="Recent lineage decline",
                severity="warn",
                confidence="medium" if trend_explorer.evidence_sufficient else "low",
                evidence=score_series.reason,
                next_action="Compare latest version against last known-good with matched opponents and eval settings.",
            )
        )

    regression_groups = [group for group in trend_explorer.submission_patterns if group.code == "regression_run"]
    if regression_groups:
        top_group = regression_groups[0]
        signals.append(
            PatternSignal(
                code="cross_submission_regression_cluster",
                title="Cross-submission regression cluster",
                severity="high" if top_group.count >= 2 else "warn",
                confidence="medium",
                evidence=top_group.evidence,
                next_action=top_group.next_action,
            )
        )

    if unsupported.has_unsupported_state:
        high_issues = [issue for issue in unsupported.issues if issue.severity in {"error", "warn"}]
        if high_issues:
            signals.append(
                PatternSignal(
                    code="unsupported_data",
                    title="Unsupported or incomplete data",
                    severity="warn",
                    confidence="high",
                    evidence=f"{len(high_issues)} unsupported-state issue(s) detected.",
                    next_action="Address unsupported-state warnings to avoid silent misdiagnosis.",
                )
            )

    if not signals:
        signals.append(
            PatternSignal(
                code="no_strong_pattern",
                title="No strong regression pattern detected",
                severity="info",
                confidence="low",
                evidence="Current signals are mixed or low-effect.",
                next_action="Collect more episodes and keep matchup mix consistent before major changes.",
            )
        )

    severity_order = {"high": 0, "warn": 1, "info": 2}
    signals.sort(key=lambda signal: severity_order.get(signal.severity, 3))

    headline = signals[0].title if signals else "Collect more evidence before extracting strong patterns."
    evidence_sufficient = any(signal.confidence in {"medium", "high"} for signal in signals)
    return PatternExtractionSummary(
        evidence_sufficient=evidence_sufficient,
        headline=headline,
        signals=signals,
    )


def compute_outcome_summary(
    current: PolicyInfo,
    season: str,
    baseline: PolicyInfo | None = None,
    min_matches_for_confidence: int = 5,
) -> OutcomeSummary:
    current_snapshot = OutcomeSnapshot(
        id=current.id,
        name=current.name,
        version=current.version,
        rank=current.rank,
        score=current.score,
        matches=current.matches,
        season=season,
    )

    if baseline is None:
        return OutcomeSummary(
            current=current_snapshot,
            reason="No previous policy version available in this policy family.",
        )

    baseline_snapshot = OutcomeSnapshot(
        id=baseline.id,
        name=baseline.name,
        version=baseline.version,
        rank=baseline.rank,
        score=baseline.score,
        matches=baseline.matches,
        season=season,
    )

    rank_delta = current.rank - baseline.rank if current.rank is not None and baseline.rank is not None else None
    score_delta_raw = (
        current.score - baseline.score if current.score is not None and baseline.score is not None else None
    )
    score_delta = round(score_delta_raw, 6) if score_delta_raw is not None else None
    matches_delta = current.matches - baseline.matches

    score_confident = (
        score_delta is not None
        and current.matches >= min_matches_for_confidence
        and baseline.matches >= min_matches_for_confidence
    )

    if score_confident:
        assert score_delta is not None
        if score_delta > 0.01:
            return OutcomeSummary(
                verdict="helped",
                reason=f"Leaderboard score improved by {score_delta:.3f} vs v{baseline.version}.",
                evidence_sufficient=True,
                current=current_snapshot,
                baseline=baseline_snapshot,
                delta=OutcomeDelta(rank_delta=rank_delta, score_delta=score_delta, matches_delta=matches_delta),
            )
        if score_delta < -0.01:
            return OutcomeSummary(
                verdict="hurt",
                reason=f"Leaderboard score dropped by {abs(score_delta):.3f} vs v{baseline.version}.",
                evidence_sufficient=True,
                current=current_snapshot,
                baseline=baseline_snapshot,
                delta=OutcomeDelta(rank_delta=rank_delta, score_delta=score_delta, matches_delta=matches_delta),
            )
        return OutcomeSummary(
            verdict="inconclusive",
            reason=f"Leaderboard score change vs v{baseline.version} is near zero ({score_delta:.3f}).",
            evidence_sufficient=True,
            current=current_snapshot,
            baseline=baseline_snapshot,
            delta=OutcomeDelta(rank_delta=rank_delta, score_delta=score_delta, matches_delta=matches_delta),
        )

    if rank_delta is not None:
        if rank_delta < 0:
            verdict = "helped"
            reason = f"Rank improved by {abs(rank_delta)} vs v{baseline.version}, but score confidence is low."
        elif rank_delta > 0:
            verdict = "hurt"
            reason = f"Rank worsened by {rank_delta} vs v{baseline.version}, but score confidence is low."
        else:
            verdict = "inconclusive"
            reason = f"Rank unchanged vs v{baseline.version}, and score confidence is low."
        return OutcomeSummary(
            verdict=verdict,
            reason=reason,
            evidence_sufficient=False,
            current=current_snapshot,
            baseline=baseline_snapshot,
            delta=OutcomeDelta(rank_delta=rank_delta, score_delta=score_delta, matches_delta=matches_delta),
        )

    return OutcomeSummary(
        verdict="inconclusive",
        reason=f"Insufficient leaderboard evidence to compare against v{baseline.version}.",
        evidence_sufficient=False,
        current=current_snapshot,
        baseline=baseline_snapshot,
        delta=OutcomeDelta(rank_delta=rank_delta, score_delta=score_delta, matches_delta=matches_delta),
    )


def compute_derived_metrics(episodes: list[DashboardEpisode]) -> DerivedMetrics:
    if not episodes:
        return DerivedMetrics()

    totals: dict[str, float] = {}
    total_steps = 0
    completed = [e for e in episodes if e.status == "completed"]

    for ep in completed:
        total_steps += ep.steps
        for key, value in ep.metrics.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value

    n_episodes = len(completed) or 1

    def get(key: str, default: float = 0.0) -> float:
        return metric_value(totals, key, default)

    # Efficiency KPIs
    move_success = get("action.move.success")
    move_failed = get("action.move.failed")
    move_efficiency = kpi_move_efficiency(totals)

    action_failed = get("action.failed")
    total_actions = kpi_action_success_total(totals) + action_failed
    action_success_rate = kpi_action_success_rate(totals)

    vibe_change_success = get("action.change_vibe.success")
    vibe_change_rate = safe_div(vibe_change_success, total_actions)

    # Resource KPIs
    total_amount = sum(get(f"{r}.amount") for r in RESOURCES)
    total_gained = sum(get(f"{r}.gained") for r in RESOURCES)
    resource_retention = kpi_resource_retention(totals)

    # Vulnerability KPIs
    frozen_ticks = get("status.frozen.ticks")
    freeze_vulnerability = safe_div(frozen_ticks, total_steps) if total_steps > 0 else 0.0

    # Junction KPIs
    junction_aligned = get("junction.aligned_by_agent")
    junction_scrambled = get("junction.scrambled_by_agent")
    junction_control_rate = kpi_junction_control_rate(totals)

    aligned_gained = get("aligned.junction.gained", junction_aligned)
    aligned_lost = get("aligned.junction.lost")
    aligned_held = get("aligned.junction.held")
    alignment_stability = safe_div(aligned_held, aligned_gained) if aligned_gained > 0 else 0.0
    net_alignment_rate = safe_div(aligned_gained - aligned_lost, aligned_gained)

    # Strategy profiles (0-100)
    profile_aggressive = min(100, (junction_scrambled / n_episodes) * 10 + (vibe_change_success / n_episodes) * 5)

    noop_count = get("action.noop.success")
    move_rate = safe_div(move_success, move_success + noop_count)
    profile_defensive = min(100, (noop_count / n_episodes / 10) + (1 - move_rate) * 50)

    profile_resource_hoarder = min(100, resource_retention * 50 + (total_amount / n_episodes / 10))

    profile_junction_hunter = min(100, (junction_aligned / n_episodes) * 3 + junction_control_rate * 50)

    noop_rate_profile = safe_div(noop_count, move_success + noop_count)
    profile_mobile_scout = min(100, move_efficiency * 50 + (1 - noop_rate_profile) * 50)

    # Additional KPIs
    noop_rate = kpi_noop_rate(totals)
    resource_efficiency_per_step = safe_div(total_gained, total_steps) if total_steps > 0 else 0.0

    heart_lost = get("heart.lost")
    hearts_to_junction_rate = safe_div(junction_aligned, heart_lost)

    rewards = [e.reward for e in completed]
    if len(rewards) >= 2:
        mean_reward = statistics.mean(rewards)
        std_reward = statistics.stdev(rewards)
        reward_consistency = max(0.0, min(1.0, 1.0 - (std_reward / mean_reward))) if mean_reward > 0 else 0.0
    else:
        reward_consistency = 0.0

    avg_reward = safe_div(sum(rewards), len(rewards))
    nonzero_count = sum(1 for r in rewards if r > 0.1)
    reward_nonzero_pct = safe_div(nonzero_count, len(rewards))

    # Diagnostics
    diagnostics = compute_diagnostics(
        episodes,
        completed,
        totals,
        total_steps,
        n_episodes,
        move_efficiency,
        move_failed,
        freeze_vulnerability,
        junction_aligned,
        vibe_change_success,
        noop_rate,
        noop_count,
        rewards,
    )

    return DerivedMetrics(
        move_efficiency=move_efficiency,
        action_success_rate=action_success_rate,
        vibe_change_rate=vibe_change_rate,
        resource_retention=resource_retention,
        freeze_vulnerability=freeze_vulnerability,
        junction_control_rate=junction_control_rate,
        alignment_stability=alignment_stability,
        net_alignment_rate=net_alignment_rate,
        avg_reward=avg_reward,
        noop_rate=noop_rate,
        resource_efficiency_per_step=resource_efficiency_per_step,
        hearts_to_junction_rate=hearts_to_junction_rate,
        reward_consistency=reward_consistency,
        reward_nonzero_pct=reward_nonzero_pct,
        profile_aggressive=profile_aggressive,
        profile_defensive=profile_defensive,
        profile_resource_hoarder=profile_resource_hoarder,
        profile_junction_hunter=profile_junction_hunter,
        profile_mobile_scout=profile_mobile_scout,
        diagnostics=diagnostics,
    )


def compute_diagnostics(
    episodes: list[DashboardEpisode],
    completed: list[DashboardEpisode],
    totals: dict[str, float],
    total_steps: int,
    n_episodes: int,
    move_efficiency: float,
    move_failed: float,
    freeze_vulnerability: float,
    junction_aligned: float,
    vibe_change_success: float,
    noop_rate: float,
    noop_count: float,
    rewards: list[float],
) -> list[str]:
    diagnostics: list[str] = []

    def get(key: str, default: float = 0.0) -> float:
        return totals.get(key, default)

    failed_count = sum(1 for e in episodes if e.status == "failed")
    if failed_count > 0:
        failed_pct = failed_count / len(episodes) * 100
        diagnostics.append(f"{failed_count} failed jobs ({failed_pct:.1f}%) - investigate reliability before rollout")

    if move_efficiency < 0.7 and move_failed > n_episodes * 10:
        diagnostics.append("High movement failures - check pathfinding or obstacle handling")

    action_timeout = get("action.timeout")
    if action_timeout > n_episodes * 5:
        timeout_per_ep = action_timeout / n_episodes
        diagnostics.append(f"Action timeouts detected ({timeout_per_ep:.1f}/ep) - policy may have latency issues")

    if freeze_vulnerability > 0.1:
        diagnostics.append(f"Spending {freeze_vulnerability * 100:.1f}% of time frozen - improve combat avoidance")

    heart_gained = get("heart.gained")
    if junction_aligned < n_episodes * 2 and heart_gained > n_episodes * 3:
        diagnostics.append("Hearts collected but low junction alignment - check aligner activation")

    if vibe_change_success == 0 and n_episodes >= 5:
        diagnostics.append("No vibe changes detected - policy may not be using change_vibe action")

    total_lost = sum(get(f"{r}.lost") for r in RESOURCES)
    total_gained = sum(get(f"{r}.gained") for r in RESOURCES)
    if total_lost > total_gained * 0.5:
        diagnostics.append("High resource loss - resources being lost faster than gained")

    avg_steps = total_steps / n_episodes if n_episodes > 0 else 0
    short_episodes = sum(1 for e in completed if e.steps < avg_steps * 0.5)
    if short_episodes > n_episodes * 0.2:
        diagnostics.append(f"{short_episodes} episodes terminated early - possible stability issues")

    if noop_rate > 0.15 and noop_count > n_episodes * 100:
        diagnostics.append(f"High noop rate ({noop_rate * 100:.1f}%) - policy may be indecisive or stuck")

    # Matchup disparity
    by_opponent: dict[str, list[float]] = {}
    for e in completed:
        by_opponent.setdefault(e.opponent_name, []).append(e.reward)
    opponent_avgs = {opp: sum(rs) / len(rs) for opp, rs in by_opponent.items() if len(rs) >= 3}
    if opponent_avgs:
        best_avg = max(opponent_avgs.values())
        worst_avg = min(opponent_avgs.values())
        if best_avg > 2.0 and worst_avg < 0.5:
            best_opp = max(opponent_avgs, key=opponent_avgs.get)  # type: ignore[arg-type]
            worst_opp = min(opponent_avgs, key=opponent_avgs.get)  # type: ignore[arg-type]
            diagnostics.append(
                f"Matchup disparity - best avg {best_avg:.1f} vs {best_opp}, worst avg {worst_avg:.1f} vs {worst_opp}"
            )

    # Declining rewards
    if len(rewards) >= 10:
        n_r = len(rewards)
        x_mean = (n_r - 1) / 2.0
        y_mean = sum(rewards) / n_r
        numerator = sum((i - x_mean) * (rewards[i] - y_mean) for i in range(n_r))
        denominator = sum((i - x_mean) ** 2 for i in range(n_r))
        if denominator > 0:
            slope = numerator / denominator
            if slope < -0.05:
                diagnostics.append(f"Declining rewards (slope={slope:.3f}) - recent episodes scoring worse")

    # High freeze + low reward
    if len(completed) >= 5:
        avg_reward_all = sum(e.reward for e in completed) / n_episodes
        frozen_low_count = sum(
            1
            for e in completed
            if e.steps > 0
            and e.metrics.get("status.frozen.ticks", 0) / e.steps > 0.15
            and e.reward < avg_reward_all * 0.5
        )
        if frozen_low_count > n_episodes * 0.15:
            diagnostics.append(
                f"High freeze time and low reward in {frozen_low_count} episodes "
                f"({frozen_low_count / n_episodes * 100:.0f}%) - check combat avoidance"
            )

    # Team comp red flag
    comp_rewards: dict[str, list[float]] = {}
    for e in completed:
        comp_rewards.setdefault(e.team_composition, []).append(e.reward)
    avg_6v2 = sum(comp_rewards.get("6v2", [])) / max(len(comp_rewards.get("6v2", [])), 1)
    avg_2v6 = sum(comp_rewards.get("2v6", [])) / max(len(comp_rewards.get("2v6", [])), 1)
    if avg_2v6 > 0 and avg_6v2 / avg_2v6 > 3.0 and len(comp_rewards.get("6v2", [])) >= 3:
        diagnostics.append(
            f"Over-reliance on agent count - 6v2 avg {avg_6v2:.1f} vs 2v6 avg {avg_2v6:.1f} "
            f"(ratio {avg_6v2 / avg_2v6:.1f}x)"
        )

    # Zero-count detection
    capability_metrics = [
        "junction.aligned_by_agent",
        "junction.scrambled_by_agent",
        "action.change_vibe.success",
    ]
    zero_capabilities = []
    for metric in capability_metrics:
        if all(metric_value(e.metrics, metric) == 0 for e in completed):
            zero_capabilities.append(metric)
    if zero_capabilities:
        names = ", ".join(zero_capabilities)
        diagnostics.append(f"Unused capabilities (always zero): {names}")

    return diagnostics


def compute_team_comp_analysis(episodes: list[DashboardEpisode]) -> list[TeamCompStats]:
    by_comp: dict[str, list[DashboardEpisode]] = {}
    for e in episodes:
        if e.status == "completed":
            by_comp.setdefault(e.team_composition, []).append(e)

    result = []
    for comp, eps in sorted(by_comp.items()):
        n = len(eps)
        avg_reward = sum(e.reward for e in eps) / n

        total_move_success = sum(metric_value(e.metrics, "action.move.success") for e in eps)
        total_move_failed = sum(metric_value(e.metrics, "action.move.failed") for e in eps)
        total_move = total_move_success + total_move_failed
        move_eff = total_move_success / total_move if total_move > 0 else 0

        avg_junction = sum(metric_value(e.metrics, "junction.aligned_by_agent") for e in eps) / n
        avg_resource = sum(sum(e.metrics.get(f"{r}.gained", 0) for r in RESOURCES) for e in eps) / n

        result.append(
            TeamCompStats(
                composition=comp,
                count=n,
                avg_reward=round(avg_reward, 4),
                avg_move_efficiency=round(move_eff, 4),
                avg_junction_aligned=round(avg_junction, 4),
                avg_resource_gained=round(avg_resource, 4),
            )
        )

    return result


def compute_opponent_metrics(episodes: list[DashboardEpisode]) -> dict[str, OpponentStats]:
    by_opponent: dict[str, list[DashboardEpisode]] = {}
    for e in episodes:
        if e.status == "completed":
            by_opponent.setdefault(e.opponent_name, []).append(e)

    result: dict[str, OpponentStats] = {}
    for opp, eps in by_opponent.items():
        n = len(eps)
        total_reward = sum(e.reward for e in eps)
        avg_reward = total_reward / n
        summed_metrics: dict[str, float] = {}
        for e in eps:
            for k, v in e.metrics.items():
                if isinstance(v, (int, float)):
                    summed_metrics[k] = summed_metrics.get(k, 0) + v

        avg_metrics = {k: v / n for k, v in summed_metrics.items()}

        m = avg_metrics
        move_s = metric_value(m, "action.move.success")
        noop = m.get("action.noop.success", 0)
        vibe = m.get("action.change_vibe.success", 0)
        j_aligned = metric_value(m, "junction.aligned_by_agent")
        j_scrambled = metric_value(m, "junction.scrambled_by_agent")
        total_amount = sum(m.get(f"{r}.amount", 0) for r in RESOURCES)
        move_eff = kpi_move_efficiency(m)
        j_control = kpi_junction_control_rate(m)
        resource_retention = kpi_resource_retention(m)
        move_rate = safe_div(move_s, move_s + noop)
        noop_rate_p = safe_div(noop, move_s + noop)
        action_success = kpi_action_success_rate(m)
        noop_rate = kpi_noop_rate(m)
        avg_metrics.update(
            {
                "kpi.move_efficiency": move_eff,
                "kpi.action_success_rate": action_success,
                "kpi.resource_retention": resource_retention,
                "kpi.junction_control_rate": j_control,
                "kpi.noop_rate": noop_rate,
            }
        )

        result[opp] = OpponentStats(
            count=n,
            total_reward=round(total_reward, 4),
            avg_reward=round(avg_reward, 4),
            avg_metrics={k: round(v, 4) for k, v in avg_metrics.items()},
            strategy_profile={
                "aggressive": round(min(100, j_scrambled * 10 + vibe * 5), 2),
                "defensive": round(min(100, noop / 10 + (1 - move_rate) * 50), 2),
                "resource_hoarder": round(min(100, resource_retention * 50 + total_amount / 10), 2),
                "junction_hunter": round(min(100, j_aligned * 3 + j_control * 50), 2),
                "mobile_scout": round(min(100, move_eff * 50 + (1 - noop_rate_p) * 50), 2),
            },
        )

    return result


def compute_matchup_summary(
    current_episodes: list[DashboardEpisode],
    baseline_episodes: list[DashboardEpisode] | None = None,
    min_slice_episodes: int = 3,
    min_total_episodes: int = 8,
) -> MatchupSummary:
    current_completed = [episode for episode in current_episodes if episode.status == "completed"]
    if not current_completed:
        return MatchupSummary(
            reason="No completed episodes available for matchup diagnosis.",
        )

    current_avg_reward = statistics.mean(episode.reward for episode in current_completed)
    baseline_completed = [episode for episode in (baseline_episodes or []) if episode.status == "completed"]
    baseline_avg_reward = (
        statistics.mean(episode.reward for episode in baseline_completed) if baseline_completed else None
    )
    global_reward_delta = (
        current_avg_reward - baseline_avg_reward
        if baseline_avg_reward is not None
        and len(current_completed) >= min_total_episodes
        and len(baseline_completed) >= min_total_episodes
        else None
    )

    def group_rewards(episodes: list[DashboardEpisode], field: str) -> dict[str, list[float]]:
        grouped: dict[str, list[float]] = {}
        for episode in episodes:
            if episode.status != "completed":
                continue
            key = episode.opponent_name if field == "opponent" else episode.team_composition
            grouped.setdefault(key, []).append(episode.reward)
        return grouped

    def build_slices(
        current_groups: dict[str, list[float]],
        baseline_groups: dict[str, list[float]],
    ) -> list[MatchupSlice]:
        rows: list[MatchupSlice] = []
        for key, rewards in current_groups.items():
            if len(rewards) < min_slice_episodes:
                continue
            current_avg = statistics.mean(rewards)
            baseline_rewards = baseline_groups.get(key, [])
            baseline_count = len(baseline_rewards) if len(baseline_rewards) >= min_slice_episodes else None
            baseline_avg = statistics.mean(baseline_rewards) if baseline_count else None
            delta_vs_baseline = current_avg - baseline_avg if baseline_avg is not None else None
            rows.append(
                MatchupSlice(
                    key=key,
                    count=len(rewards),
                    avg_reward=round(current_avg, 4),
                    delta_vs_policy=round(current_avg - current_avg_reward, 4),
                    baseline_count=baseline_count,
                    baseline_avg_reward=round(baseline_avg, 4) if baseline_avg is not None else None,
                    delta_vs_baseline=round(delta_vs_baseline, 4) if delta_vs_baseline is not None else None,
                )
            )
        rows.sort(key=lambda row: row.avg_reward)
        return rows

    current_opponents = group_rewards(current_completed, "opponent")
    baseline_opponents = group_rewards(baseline_completed, "opponent")
    opponent_slices = build_slices(current_opponents, baseline_opponents)

    current_compositions = group_rewards(current_completed, "composition")
    baseline_compositions = group_rewards(baseline_completed, "composition")
    composition_slices = build_slices(current_compositions, baseline_compositions)

    opponent_spread = 0.0
    best_opponent: str | None = None
    worst_opponent: str | None = None
    if len(opponent_slices) >= 2:
        worst = opponent_slices[0]
        best = opponent_slices[-1]
        opponent_spread = best.avg_reward - worst.avg_reward
        best_opponent = best.key
        worst_opponent = worst.key
    elif len(opponent_slices) == 1:
        best_opponent = opponent_slices[0].key
        worst_opponent = opponent_slices[0].key

    composition_spread = 0.0
    best_composition: str | None = None
    worst_composition: str | None = None
    if len(composition_slices) >= 2:
        worst_comp = composition_slices[0]
        best_comp = composition_slices[-1]
        composition_spread = best_comp.avg_reward - worst_comp.avg_reward
        best_composition = best_comp.key
        worst_composition = worst_comp.key
    elif len(composition_slices) == 1:
        best_composition = composition_slices[0].key
        worst_composition = composition_slices[0].key

    matched_opponent_slices = [row for row in opponent_slices if row.delta_vs_baseline is not None]
    matched_composition_slices = [row for row in composition_slices if row.delta_vs_baseline is not None]
    evidence_sufficient = global_reward_delta is not None and (
        len(matched_opponent_slices) >= 2 or len(matched_composition_slices) >= 2
    )

    interaction_specific_issue = False
    reason: str

    if not evidence_sufficient:
        if baseline_episodes:
            reason = "Insufficient matched matchup slices vs baseline. Collect more overlap before strong claims."
        elif len(opponent_slices) >= 2 and opponent_spread >= 0.5:
            reason = (
                f"Large within-submission matchup spread ({opponent_spread:.2f}) "
                f"from {worst_opponent} to {best_opponent}. Inspect worst slices first."
            )
        else:
            reason = "Matchup evidence is limited; collect more episodes before making matchup-specific claims."
    else:
        opponent_reason: str | None = None
        if matched_opponent_slices:
            worst_opponent_row = min(
                matched_opponent_slices,
                key=lambda row: row.delta_vs_baseline if row.delta_vs_baseline is not None else 0,
            )
            other_opponent_deltas = [
                row.delta_vs_baseline
                for row in matched_opponent_slices
                if row.key != worst_opponent_row.key and row.delta_vs_baseline is not None
            ]
            other_opponent_delta_avg = (
                statistics.mean(other_opponent_deltas)
                if other_opponent_deltas
                else worst_opponent_row.delta_vs_baseline
            )
            if (
                global_reward_delta is not None
                and global_reward_delta <= -0.1
                and (worst_opponent_row.delta_vs_baseline or 0) <= -0.3
                and (other_opponent_delta_avg or 0) >= -0.05
            ):
                interaction_specific_issue = True
                opponent_reason = (
                    "Regression is concentrated vs "
                    f"{worst_opponent_row.key} ({worst_opponent_row.delta_vs_baseline:+.2f}) "
                    f"while other opponents are comparatively stable ({other_opponent_delta_avg:+.2f})."
                )

        composition_reason: str | None = None
        if not interaction_specific_issue and matched_composition_slices:
            worst_comp_row = min(
                matched_composition_slices,
                key=lambda row: row.delta_vs_baseline if row.delta_vs_baseline is not None else 0,
            )
            other_comp_deltas = [
                row.delta_vs_baseline
                for row in matched_composition_slices
                if row.key != worst_comp_row.key and row.delta_vs_baseline is not None
            ]
            other_comp_delta_avg = (
                statistics.mean(other_comp_deltas) if other_comp_deltas else worst_comp_row.delta_vs_baseline
            )
            if (
                global_reward_delta is not None
                and global_reward_delta <= -0.1
                and (worst_comp_row.delta_vs_baseline or 0) <= -0.3
                and (other_comp_delta_avg or 0) >= -0.05
            ):
                interaction_specific_issue = True
                composition_reason = (
                    "Regression is concentrated in team composition "
                    f"{worst_comp_row.key} ({worst_comp_row.delta_vs_baseline:+.2f}) "
                    f"while other compositions are comparatively stable ({other_comp_delta_avg:+.2f})."
                )

        if interaction_specific_issue:
            reason = opponent_reason or composition_reason or "Interaction-specific regression detected."
        elif global_reward_delta is not None and global_reward_delta <= -0.1:
            reason = (
                f"Regression appears broad across slices (global reward delta {global_reward_delta:+.2f}). "
                "Prioritize global behavior fixes before matchup-specific tuning."
            )
        elif global_reward_delta is not None and global_reward_delta >= 0.1:
            reason = f"Matchups improved overall (global reward delta {global_reward_delta:+.2f})."
        else:
            reason = (
                f"Overall change is small (global reward delta {global_reward_delta:+.2f}). "
                "Monitor worst matchup slices for drift."
            )

    return MatchupSummary(
        evidence_sufficient=evidence_sufficient,
        interaction_specific_issue=interaction_specific_issue,
        reason=reason,
        current_avg_reward=round(current_avg_reward, 4),
        baseline_avg_reward=round(baseline_avg_reward, 4) if baseline_avg_reward is not None else None,
        global_reward_delta=round(global_reward_delta, 4) if global_reward_delta is not None else None,
        opponent_spread=round(opponent_spread, 4),
        best_opponent=best_opponent,
        worst_opponent=worst_opponent,
        composition_spread=round(composition_spread, 4),
        best_composition=best_composition,
        worst_composition=worst_composition,
        opponent_slices=opponent_slices,
        composition_slices=composition_slices,
    )


def compute_failure_summary(episodes: list[DashboardEpisode]) -> FailureSummary:
    if not episodes:
        return FailureSummary()

    completed = [e for e in episodes if e.status == "completed"]
    failed = [e for e in episodes if e.status == "failed"]

    timeout_failures = 0
    oom_failures = 0
    crash_failures = 0
    other_failures = 0
    for episode in failed:
        error_type = (episode.error_type or "").lower()
        if "timeout" in error_type:
            timeout_failures += 1
            continue
        if "oom" in error_type:
            oom_failures += 1
            continue
        if "crash" in error_type or "policy" in error_type or "exception" in error_type or "error" in error_type:
            crash_failures += 1
            continue
        other_failures += 1

    freeze_heavy_completed = 0
    noop_heavy_completed = 0
    for episode in completed:
        if episode.steps > 0:
            frozen_ticks = float(episode.metrics.get("status.frozen.ticks", 0))
            if frozen_ticks / episode.steps >= 0.15:
                freeze_heavy_completed += 1

        total_action_success = sum(
            float(value)
            for key, value in episode.metrics.items()
            if key.startswith("action.") and key.endswith(".success") and isinstance(value, (int, float))
        )
        action_failed = float(episode.metrics.get("action.failed", 0))
        total_actions = total_action_success + action_failed
        noop_count = float(episode.metrics.get("action.noop.success", 0))
        if total_actions > 0 and noop_count / total_actions >= 0.4:
            noop_heavy_completed += 1

    total_episodes = len(episodes)
    failed_episodes = len(failed)
    return FailureSummary(
        total_episodes=total_episodes,
        completed_episodes=len(completed),
        failed_episodes=failed_episodes,
        failed_rate=safe_div(failed_episodes, total_episodes),
        timeout_failures=timeout_failures,
        oom_failures=oom_failures,
        crash_failures=crash_failures,
        other_failures=other_failures,
        freeze_heavy_completed=freeze_heavy_completed,
        noop_heavy_completed=noop_heavy_completed,
    )


def compute_crash_dump_summary(
    episodes: list[DashboardEpisode],
    max_entries: int = 12,
    max_signatures: int = 6,
) -> CrashDumpSummary:
    failed = [episode for episode in episodes if episode.status == "failed"]
    if not failed:
        return CrashDumpSummary()

    grouped: dict[str, CrashDumpSignature] = {}

    def normalize_message(message: str | None) -> str:
        if not message:
            return ""
        first_line = message.strip().splitlines()[0]
        if not first_line:
            return ""
        return " ".join(first_line.split())[:120]

    entries: list[CrashDumpEntry] = []
    for idx, episode in enumerate(failed):
        run_number = episode.raw_tags.get("run_number")
        analysis_command = (
            f"cogames analyze {run_number}" if run_number else f"cogames analyze --job-id {episode.job_id}"
        )
        if idx < max_entries:
            entries.append(
                CrashDumpEntry(
                    episode_id=episode.episode_id,
                    job_id=episode.job_id,
                    created_at=episode.created_at,
                    error_type=episode.error_type,
                    error_message=episode.error_message,
                    analysis_command=analysis_command,
                    replay_url=episode.replay_url,
                )
            )

        error_type = (episode.error_type or "unknown").strip().lower() or "unknown"
        normalized_message = normalize_message(episode.error_message)
        signature_key = f"{error_type}:{normalized_message}" if normalized_message else error_type
        if signature_key not in grouped:
            grouped[signature_key] = CrashDumpSignature(
                signature=signature_key,
                count=0,
                error_type=error_type,
                example_message=normalized_message or None,
            )
        grouped[signature_key].count += 1

    signatures = sorted(grouped.values(), key=lambda signature: (-signature.count, signature.signature))
    top_signatures = signatures[:max_signatures]

    if top_signatures:
        top_signature = top_signatures[0]
        headline = (
            f"{len(failed)} failed runs sampled. Top signature `{top_signature.error_type}` "
            f"appears {top_signature.count} times."
        )
    else:
        headline = f"{len(failed)} failed runs sampled. No error signatures extracted."

    return CrashDumpSummary(
        evidence_sufficient=True,
        headline=headline,
        total_failed=len(failed),
        signatures=top_signatures,
        entries=entries,
    )


def compute_stats_inventory_summary(
    episodes: list[DashboardEpisode],
    top_n: int = 12,
) -> StatsInventorySummary:
    if not episodes:
        return StatsInventorySummary(
            notes=["No episodes available; collect evaluation outputs before stats inventory analysis."],
        )

    completed = [episode for episode in episodes if episode.status == "completed"]
    failed = [episode for episode in episodes if episode.status == "failed"]
    metric_total = len(completed)
    tag_total = len(episodes)

    metric_counts: dict[str, int] = {}
    for episode in completed:
        for key in episode.metrics:
            metric_counts[key] = metric_counts.get(key, 0) + 1

    tag_counts: dict[str, int] = {}
    for episode in episodes:
        for key, value in episode.raw_tags.items():
            if value:
                tag_counts[key] = tag_counts.get(key, 0) + 1

    top_metric_keys = sorted(metric_counts.items(), key=lambda item: (-item[1], item[0]))[:top_n]
    top_tag_keys = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:top_n]

    metric_rows = [
        StatsInventoryField(
            key=key,
            kind="metric",
            present_count=count,
            total_count=metric_total,
            coverage=round(safe_div(count, metric_total), 4) if metric_total > 0 else 0.0,
        )
        for key, count in top_metric_keys
    ]
    tag_rows = [
        StatsInventoryField(
            key=key,
            kind="tag",
            present_count=count,
            total_count=tag_total,
            coverage=round(safe_div(count, tag_total), 4),
        )
        for key, count in top_tag_keys
    ]

    notes: list[str] = []
    if metric_total == 0:
        notes.append("No completed episodes were sampled, so metric coverage is unavailable.")
    else:
        notes.append("Use top metric coverage to spot missing signals before deeper diagnosis.")
    if not tag_rows:
        notes.append("No non-empty tags detected; add run metadata tags for better replay slicing and auditability.")

    return StatsInventorySummary(
        total_episodes=len(episodes),
        completed_episodes=len(completed),
        failed_episodes=len(failed),
        distinct_metric_keys=len(metric_counts),
        distinct_tag_keys=len(tag_counts),
        top_metric_keys=metric_rows,
        top_tag_keys=tag_rows,
        notes=notes,
    )


def compute_action_summary(outcome: OutcomeSummary, failures: FailureSummary) -> ActionSummary:
    if not outcome.evidence_sufficient:
        return ActionSummary(
            rollout_recommendation="hold",
            headline="Evidence is insufficient for strong prescriptions.",
            actions=[
                "Collect more evaluation evidence (target at least 5 matched samples for current and baseline).",
                "Keep matchup mix consistent while collecting evidence to avoid confounded deltas.",
                "Re-run diagnosis after additional episodes before changing rollout policy.",
            ],
        )

    if failures.timeout_failures > 0 or failures.oom_failures > 0 or failures.failed_rate >= 0.1:
        return ActionSummary(
            rollout_recommendation="block",
            headline="Reliability regression risk detected. Fix reliability before rollout.",
            actions=[
                "Prioritize timeout/OOM/crash root-cause analysis using failed job IDs.",
                "Apply reliability fix and re-run the same evaluation slice for comparison.",
                "Only proceed once failure rate and timeout/OOM counts return near baseline.",
            ],
        )

    if outcome.verdict == "hurt":
        return ActionSummary(
            rollout_recommendation="hold",
            headline="Performance regressed vs baseline. Hold rollout.",
            actions=[
                "Start with worst matchup and lowest-reward episodes to isolate behavior regressions.",
                (
                    "Target one dominant driver first "
                    "(junction control, reward non-zero rate, or noop/freeze pathologies)."
                ),
                "Ship a focused experiment and compare deltas against the same baseline/version pairing.",
            ],
        )

    if outcome.verdict == "helped":
        return ActionSummary(
            rollout_recommendation="proceed_cautiously",
            headline="Submission improved leaderboard performance.",
            actions=[
                "Proceed with guarded rollout while monitoring failure and timeout rates.",
                "Run one validation pack on recent opponent mix to confirm stability.",
                "If reliability drifts upward, revert and prioritize performance-safe optimizations.",
            ],
        )

    return ActionSummary(
        rollout_recommendation="hold",
        headline="Outcome is inconclusive. Gather targeted evidence before changing rollout state.",
        actions=[
            "Increase sample size for the current submission and baseline.",
            "Inspect matchup-specific slices to determine whether regression is global or interaction-specific.",
            "Re-evaluate once confidence criteria are met.",
        ],
    )


def compute_orchestration_hooks(
    policy: PolicyInfo,
    outcome: OutcomeSummary,
    failures: FailureSummary,
    actions: ActionSummary,
    matchup: MatchupSummary,
    confidence: ConfidenceSummary,
    patterns: PatternExtractionSummary,
) -> OrchestrationHookSummary:
    hooks: list[OrchestrationExperimentHook] = []
    priority = 1
    pattern_codes = {signal.code for signal in patterns.signals}

    def add_hook(
        hook_id: str,
        title: str,
        objective: str,
        rationale: str,
        hook_actions: list[str],
        acceptance_checks: list[str],
    ) -> None:
        nonlocal priority
        hooks.append(
            OrchestrationExperimentHook(
                id=hook_id,
                priority=priority,
                title=title,
                objective=objective,
                rationale=rationale,
                actions=hook_actions,
                acceptance_checks=acceptance_checks,
            )
        )
        priority += 1

    if not confidence.evidence_sufficient:
        add_hook(
            hook_id="collect_more_evidence_pack",
            title="Collect matched evidence pack",
            objective="Raise confidence before strong prescriptions.",
            rationale="Confidence intervals are inconclusive or undersampled.",
            hook_actions=confidence.recommended_actions[:3],
            acceptance_checks=[
                "At least one key confidence interval no longer crosses zero.",
                "Matched baseline/current sample sizes meet minimum threshold.",
            ],
        )

    if (
        failures.timeout_failures > 0
        or failures.oom_failures > 0
        or failures.failed_rate >= 0.1
        or "reliability_risk" in pattern_codes
    ):
        add_hook(
            hook_id="reliability_recovery_pack",
            title="Reliability recovery pack",
            objective="Reduce timeout/OOM/crash rates before rollout.",
            rationale=(
                f"Failure rate is {failures.failed_rate * 100:.1f}% "
                f"(timeouts={failures.timeout_failures}, oom={failures.oom_failures})."
            ),
            hook_actions=[
                "Re-run with reduced inference load and profiling enabled.",
                "Compare failure deltas on the same opponent/composition slice.",
                "Keep behavior changes minimal while reliability is unstable.",
            ],
            acceptance_checks=[
                "Failure-rate delta confidence interval is <= 0.",
                "Timeout/OOM counts return near baseline levels.",
            ],
        )

    if matchup.interaction_specific_issue:
        add_hook(
            hook_id="interaction_slice_patch",
            title="Interaction-specific patch pack",
            objective="Patch the worst matchup/composition without global regression.",
            rationale=matchup.reason,
            hook_actions=[
                "Generate focused eval slice for worst opponent/composition.",
                "Inspect lowest-reward replays in that slice before policy changes.",
                "Apply targeted adjustment and re-evaluate full pack.",
            ],
            acceptance_checks=[
                "Worst-slice reward improves with neutral/positive global delta.",
                "No reliability regression in patched runs.",
            ],
        )

    if (
        outcome.verdict == "hurt" and not matchup.interaction_specific_issue
    ) or "cross_submission_regression_cluster" in pattern_codes:
        add_hook(
            hook_id="global_regression_patch",
            title="Global regression patch pack",
            objective="Reverse global score decline against baseline.",
            rationale=outcome.reason,
            hook_actions=[
                "Patch the dominant global driver identified in pattern signals.",
                "Run matched baseline comparator pack before and after patch.",
                "Promote only if score and reliability gates both improve.",
            ],
            acceptance_checks=[
                "Score delta confidence interval shifts positive.",
                "Rollout recommendation is no longer `hold`/`block`.",
            ],
        )

    if outcome.verdict == "helped" and failures.failed_rate < 0.1:
        add_hook(
            hook_id="guarded_rollout_validation",
            title="Guarded rollout validation pack",
            objective="Validate gains under current matchup mix before promotion.",
            rationale=actions.headline,
            hook_actions=[
                "Run one validation pack with current population/opponent distribution.",
                "Track confidence intervals for reward and failure deltas.",
                "Proceed only if reliability guardrails stay green.",
            ],
            acceptance_checks=[
                "Reward delta interval remains positive or neutral.",
                "Failure-rate interval does not regress.",
            ],
        )

    if not hooks:
        add_hook(
            hook_id="baseline_recheck",
            title="Baseline recheck pack",
            objective="Stabilize diagnosis state before larger experiments.",
            rationale="Signals are mixed and no strong pattern is currently actionable.",
            hook_actions=[
                "Collect a fresh matched pack against the current baseline.",
                "Recompute trend, confidence, and pattern summaries.",
            ],
            acceptance_checks=[
                "At least one high-confidence signal appears in the updated summary.",
            ],
        )

    mode = "ready" if confidence.evidence_sufficient else "collect_more_evidence"
    headline = (
        "Orchestration hooks are ready for execution."
        if mode == "ready"
        else "Confidence is limited; execute evidence-collection hooks first."
    )
    return OrchestrationHookSummary(
        evidence_sufficient=(mode == "ready"),
        mode=mode,
        headline=headline,
        experiments=hooks,
        payload_template=OrchestrationPayloadTemplate(
            policy_version_id=policy.id,
            rollout_gate=actions.rollout_recommendation,
            mode=mode,
            experiment_ids=[hook.id for hook in hooks],
        ),
    )


# === Claude analysis helpers ===


_CORRELATION_METRICS = [
    "action.move.success",
    "action.move.failed",
    "action.noop.success",
    "junction.aligned_by_agent",
    "junction.scrambled_by_agent",
    "status.frozen.ticks",
    "heart.gained",
    "carbon.gained",
    "action.change_vibe.success",
]


def _build_episode_snapshot(episode: DashboardEpisode) -> dict[str, Any]:
    metrics = episode.metrics
    return {
        "id": episode.episode_id,
        "opp": episode.opponent_name,
        "comp": episode.team_composition,
        "r": round(episode.reward, 2),
        "steps": episode.steps,
        "mv_s": round(metric_value(metrics, "action.move.success")),
        "mv_f": round(metric_value(metrics, "action.move.failed")),
        "noop": round(metrics.get("action.noop.success", 0)),
        "frz": round(metrics.get("status.frozen.ticks", 0)),
        "j_aln": round(metric_value(metrics, "junction.aligned_by_agent")),
        "replay_url": episode.replay_url,
    }


def compute_episode_logs(completed: list[DashboardEpisode]) -> dict[str, Any]:
    if not completed:
        return {}

    episode_count = len(completed)
    rewards = [episode.reward for episode in completed]
    correlations: dict[str, float] = {}
    if episode_count >= 5:
        mean_reward = sum(rewards) / episode_count
        for metric in _CORRELATION_METRICS:
            values = [metric_value(episode.metrics, metric) for episode in completed]
            mean_value = sum(values) / episode_count
            covariance = sum((rewards[i] - mean_reward) * (values[i] - mean_value) for i in range(episode_count))
            reward_variance = sum((reward - mean_reward) ** 2 for reward in rewards)
            value_variance = sum((value - mean_value) ** 2 for value in values)
            denominator = (reward_variance * value_variance) ** 0.5
            if denominator > 0:
                correlations[metric] = round(covariance / denominator, 4)

    sorted_episodes = sorted(completed, key=lambda episode: episode.reward)
    bucket_size = max(1, episode_count // 5)
    bottom_episodes = sorted_episodes[:bucket_size]
    top_episodes = sorted_episodes[-bucket_size:]

    def average_metrics(episodes: list[DashboardEpisode]) -> dict[str, float]:
        if not episodes:
            return {}
        aggregated: dict[str, float] = {}
        for episode in episodes:
            for key, value in episode.metrics.items():
                if isinstance(value, (int, float)):
                    aggregated[key] = aggregated.get(key, 0) + value
        divisor = len(episodes)
        return {key: round(value / divisor, 2) for key, value in aggregated.items()}

    top_vs_bottom = {
        "top_20_avg_reward": round(sum(episode.reward for episode in top_episodes) / len(top_episodes), 4),
        "bottom_20_avg_reward": round(sum(episode.reward for episode in bottom_episodes) / len(bottom_episodes), 4),
        "top_20_metrics": average_metrics(top_episodes),
        "bottom_20_metrics": average_metrics(bottom_episodes),
    }

    seen_episode_ids: set[str] = set()
    snapshots: list[dict[str, Any]] = []

    def add_episodes(episodes: list[DashboardEpisode], bucket: str, max_count: int) -> None:
        for episode in episodes:
            if episode.episode_id in seen_episode_ids or len(snapshots) >= 16:
                continue
            seen_episode_ids.add(episode.episode_id)
            snapshot = _build_episode_snapshot(episode)
            snapshot["bucket"] = bucket
            snapshots.append(snapshot)
            if sum(1 for current in snapshots if current["bucket"] == bucket) >= max_count:
                break

    add_episodes(sorted_episodes[-5:][::-1], "top", 5)
    add_episodes(sorted_episodes[:5], "bottom", 5)

    episodes_by_opponent: dict[str, list[DashboardEpisode]] = {}
    for episode in completed:
        episodes_by_opponent.setdefault(episode.opponent_name, []).append(episode)
    opponent_averages = {
        opponent: sum(episode.reward for episode in episodes) / len(episodes)
        for opponent, episodes in episodes_by_opponent.items()
        if len(episodes) >= 2
    }
    if opponent_averages:
        worst_opponent = min(opponent_averages, key=lambda opponent: opponent_averages[opponent])
        worst_matchup_episodes = sorted(episodes_by_opponent[worst_opponent], key=lambda episode: episode.reward)
        add_episodes(worst_matchup_episodes[:3], "worst_matchup", 3)

    freeze_sorted = sorted(
        completed,
        key=lambda episode: episode.metrics.get("status.frozen.ticks", 0),
        reverse=True,
    )
    add_episodes(freeze_sorted[:3], "outlier", 3)

    return {
        "reward_correlations": correlations,
        "top_vs_bottom": top_vs_bottom,
        "episode_snapshots": snapshots,
    }


def build_analysis_summary(
    policy_info: PolicyInfo,
    episodes: list[DashboardEpisode],
    derived: DerivedMetrics,
    season: str,
) -> dict[str, Any]:
    completed = [e for e in episodes if e.status == "completed"]
    rewards = [e.reward for e in completed]
    failures = compute_failure_summary(episodes)
    outcome = compute_outcome_summary(policy_info, season)
    actions = compute_action_summary(outcome, failures)
    matchup = compute_matchup_summary(episodes)
    unsupported = compute_unsupported_state(episodes)
    instrumentation = compute_instrumentation_validation(episodes)
    stats_inventory = compute_stats_inventory_summary(episodes)
    confidence = compute_confidence_summary(episodes, [])
    crash_dump = compute_crash_dump_summary(episodes)
    trend = compute_version_trend_summary([policy_info])
    trend_explorer = compute_trend_explorer_summary([policy_info])
    patterns = compute_pattern_extraction_summary(
        outcome,
        failures,
        matchup,
        instrumentation,
        trend_explorer,
        unsupported,
    )
    orchestration = compute_orchestration_hooks(
        policy_info,
        outcome,
        failures,
        actions,
        matchup,
        confidence,
        patterns,
    )

    opponent_summary = {
        opponent: {
            "count": stats.count,
            "avg_reward": stats.avg_reward,
            "strategy_profile": stats.strategy_profile,
        }
        for opponent, stats in compute_opponent_metrics(episodes).items()
    }
    team_comp = {
        row.composition: {"count": row.count, "avg_reward": row.avg_reward}
        for row in compute_team_comp_analysis(episodes)
    }

    # Reward distribution
    reward_stats: dict[str, float] = {}
    if rewards:
        reward_stats = {
            "mean": round(statistics.mean(rewards), 4),
            "median": round(statistics.median(rewards), 4),
            "min": round(min(rewards), 4),
            "max": round(max(rewards), 4),
            "p25": round(sorted(rewards)[len(rewards) // 4], 4),
            "p75": round(sorted(rewards)[3 * len(rewards) // 4], 4),
        }
        if len(rewards) >= 2:
            reward_stats["std"] = round(statistics.stdev(rewards), 4)

    d = derived
    return {
        "policy": policy_info.model_dump(),
        "episode_count": len(episodes),
        "completed_count": len(completed),
        "season": season,
        "kpis": {
            "avg_reward": round(d.avg_reward, 4),
            "move_efficiency": round(d.move_efficiency, 4),
            "action_success_rate": round(d.action_success_rate, 4),
            "vibe_change_rate": round(d.vibe_change_rate, 4),
            "resource_retention": round(d.resource_retention, 4),
            "freeze_vulnerability": round(d.freeze_vulnerability, 4),
            "junction_control_rate": round(d.junction_control_rate, 4),
            "alignment_stability": round(d.alignment_stability, 4),
            "net_alignment_rate": round(d.net_alignment_rate, 4),
            "noop_rate": round(d.noop_rate, 4),
            "resource_efficiency_per_step": round(d.resource_efficiency_per_step, 4),
            "hearts_to_junction_rate": round(d.hearts_to_junction_rate, 4),
            "reward_consistency": round(d.reward_consistency, 4),
            "reward_nonzero_pct": round(d.reward_nonzero_pct, 4),
        },
        "strategy_profile": {
            "aggressive": round(d.profile_aggressive, 2),
            "defensive": round(d.profile_defensive, 2),
            "resource_hoarder": round(d.profile_resource_hoarder, 2),
            "junction_hunter": round(d.profile_junction_hunter, 2),
            "mobile_scout": round(d.profile_mobile_scout, 2),
        },
        "diagnostics": d.diagnostics,
        "outcome": outcome.model_dump(),
        "failures": failures.model_dump(),
        "actions": actions.model_dump(),
        "matchup": matchup.model_dump(),
        "unsupported": unsupported.model_dump(),
        "instrumentation": instrumentation.model_dump(),
        "stats_inventory": stats_inventory.model_dump(),
        "confidence": confidence.model_dump(),
        "crash_dump": crash_dump.model_dump(),
        "orchestration": orchestration.model_dump(),
        "trend": trend.model_dump(),
        "trend_explorer": trend_explorer.model_dump(),
        "patterns": patterns.model_dump(),
        "team_comp": team_comp,
        "opponents": opponent_summary,
        "reward_distribution": reward_stats,
    }


# Cache the analysis guide at import time to avoid request-time file I/O.
_ANALYSIS_GUIDE_PATH = Path(__file__).parents[4] / "skills" / "cg.policy-dashboard" / "analysis-guide.md"
_ANALYSIS_GUIDE = (
    _ANALYSIS_GUIDE_PATH.read_text()
    if _ANALYSIS_GUIDE_PATH.exists()
    else "Analyze the policy metrics and provide strategic advice for CoGames tournament play."
)


def build_analysis_prompt(summary: dict[str, Any]) -> str:
    summary_json = json.dumps(summary, indent=2)

    sections = [
        "You are a CoGames tournament policy analyst.",
        "Analyze the following policy performance data and provide strategic advice.",
        "",
        "## Reference Guide",
        "",
        _ANALYSIS_GUIDE,
        "",
        "## Policy Performance Summary",
        "",
        f"```json\n{summary_json}\n```",
        "",
        "## Instructions",
        "",
        "Produce a markdown analysis with exactly these"
        " 4 sections. Do NOT repeat diagnostic messages"
        " verbatim — synthesize them into root causes"
        " and actionable advice.",
        "",
        "### Root Cause Analysis",
        "Connect multiple diagnostics and metrics to"
        " identify underlying causes. Look for patterns"
        " across KPIs, matchups, and team compositions"
        " that point to the same root issue.",
        "",
        "### Top 3 Training Priorities",
        "Rank by expected ROI. For each priority, specify"
        " concrete changes: reward shaping adjustments,"
        " curriculum modifications, hyperparameter changes,"
        " or architectural improvements.",
        "",
        "### Opponent Adaptation",
        "For low-performing matchups, analyze the"
        " opponent's strategy profile and suggest"
        " counter-strategies. If no matchup data exists,"
        " skip this section.",
        "",
        "### Policy Narrative",
        "A plain-language description (2-3 sentences) of"
        ' what this policy "feels like" — its personality,'
        " strengths, and blind spots. Write this for"
        " someone who hasn't seen the data.",
    ]
    return "\n".join(sections)
