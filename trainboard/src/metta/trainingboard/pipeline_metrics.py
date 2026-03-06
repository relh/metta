from __future__ import annotations

import importlib
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from itertools import islice
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from metta.trainingboard.models import (
    CogsguardTrainDefaultsAudit,
    LaunchReliabilityAudit,
    LLMTaskScores,
    LossInventoryAudit,
    MeaningfulResultMetrics,
    MultiPolicySupportAudit,
    PipelineAssessment,
    PipelineFamilyShare,
    ResearchFunnelSnapshot,
    ResearchFunnelStages,
    ResearchPaperRecord,
    SearchCoverageMetrics,
    TrainingExperimentMetrics,
    TrainingPipelineAssessments,
    TrainingPipelineAuditSnapshot,
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
_ASSIGNMENT_PATTERN_TEMPLATE = r"^{name}(?:\s*:[^=]+)?\s*=\s*(?P<value>.+)$"


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
    states = ("running", "finished", "crashed")
    with ThreadPoolExecutor(max_workers=len(states)) as executor:
        state_to_samples = {
            state: executor.submit(
                _fetch_wandb_state_slice,
                entity=entity,
                project=project,
                state=state,
                per_state_limit=per_state_limit,
                metric_keys=metric_keys,
            )
            for state in states
        }
    samples: list[WandbRunSample] = []
    for state in states:
        samples.extend(state_to_samples[state].result())
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
    assessments = _build_pipeline_assessments(
        experiments=experiments,
        search_coverage=search_coverage,
        meaningful=meaningful,
    )
    return TrainingPipelineSnapshot(
        generated_at=now.isoformat(),
        available=True,
        source="wandb_state_samples",
        notes=[f"samples={len(samples)} (running/finished/crashed state slices)"],
        experiments=experiments,
        search_coverage=search_coverage,
        meaningful_results=meaningful,
        assessments=assessments,
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


def build_training_pipeline_audit_snapshot() -> TrainingPipelineAuditSnapshot:
    now = datetime.now(tz=UTC).isoformat()
    repo_root = _discover_repo_root()
    cogsguard_recipe_path = repo_root / "recipes" / "experiment" / "cogsguard.py"
    coggernaut_recipe_path = repo_root / "recipes" / "experiment" / "coggernaut.py"

    cogsguard_text = cogsguard_recipe_path.read_text(encoding="utf-8")
    coggernaut_text = coggernaut_recipe_path.read_text(encoding="utf-8")

    default_layout = _extract_assignment_string(cogsguard_text, "DEFAULT_LAYOUT", default="machina_1")
    default_num_agents = _extract_assignment_int(cogsguard_text, "DEFAULT_NUM_AGENTS", default=8)
    default_max_steps = _extract_assignment_int(cogsguard_text, "DEFAULT_MAX_STEPS", default=10_000)
    progress_metric = _extract_progress_metric(cogsguard_text)

    cogsguard_defaults = CogsguardTrainDefaultsAudit(
        command="uv run ./tools/run.py train cogsguard run=<run_name>",
        default_layout=default_layout,
        default_num_agents=default_num_agents,
        default_max_steps=default_max_steps,
        default_policy_assets=["learner0"],
        default_losses=["ppo_critic", "ppo_actor"],
        conditional_losses=[
            "ppo_vibe_actor (enabled when vibe actions are present)",
            "diff_horde (enabled when cumulants are configured)",
            "teacher-phase losses (enabled when teacher.enabled=true)",
        ],
        progress_metric=progress_metric,
    )

    multi_policy_example_policies = _extract_quoted_identifiers(coggernaut_text, suffix="_policy")
    multi_policy_example_slices = _extract_quoted_identifiers(coggernaut_text, suffix="_slice")
    multi_policy = MultiPolicySupportAudit(
        supported=True,
        mechanism="TrainTool.policy_assets + TrajectoryIsolation slices with per-slice policy/loss routing.",
        evidence_paths=[
            "metta/tools/train.py",
            "metta/rl/training/trajectory_isolation.py",
            "recipes/experiment/coggernaut.py",
        ],
        example_recipe="recipes/experiment/coggernaut.py::train",
        example_policies=multi_policy_example_policies,
        example_slices=multi_policy_example_slices,
    )

    launch_reliability = LaunchReliabilityAudit(
        has_automatic_retry=False,
        retry_strategy="No built-in smart retry in TrainTool; failures bubble to caller/orchestrator.",
        notes=[
            "TrainTool.invoke returns non-zero on exception and does not retry automatically.",
            "Current launch flow requires external automation for hyperparameter retry policies.",
        ],
    )

    loss_inventory = LossInventoryAudit(
        recipe_loss_keys=_collect_recipe_loss_keys(repo_root=repo_root),
        core_loss_modules=_collect_core_loss_modules(repo_root=repo_root),
    )

    return TrainingPipelineAuditSnapshot(
        generated_at=now,
        supports_multi_policy_training=True,
        cogsguard_train_defaults=cogsguard_defaults,
        multi_policy=multi_policy,
        launch_reliability=launch_reliability,
        loss_inventory=loss_inventory,
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


def _build_pipeline_assessments(
    *,
    experiments: TrainingExperimentMetrics,
    search_coverage: SearchCoverageMetrics,
    meaningful: MeaningfulResultMetrics,
) -> TrainingPipelineAssessments:
    if experiments.running_now >= 4:
        concurrent = PipelineAssessment(
            status="good",
            headline="Parallel experimentation is healthy.",
            detail=f"{experiments.running_now} runs are active now.",
        )
    elif experiments.running_now >= 1:
        concurrent = PipelineAssessment(
            status="thin",
            headline="Parallel experimentation is thin.",
            detail=f"{experiments.running_now} runs are active now; more concurrent probes would improve coverage.",
        )
    else:
        concurrent = PipelineAssessment(
            status="critical",
            headline="No active experiments detected.",
            detail="Pipeline throughput is currently idle.",
        )

    if (
        search_coverage.unique_families_30d >= 10
        and search_coverage.top_family_share_30d <= 0.40
        and search_coverage.family_entropy_30d >= 0.60
    ):
        coverage = PipelineAssessment(
            status="good",
            headline="Search space coverage is broad.",
            detail=(
                f"{search_coverage.unique_families_30d} run families in 30d, "
                f"top family share {search_coverage.top_family_share_30d:.1%}."
            ),
        )
    elif search_coverage.unique_families_30d >= 3 and search_coverage.family_entropy_30d >= 0.25:
        coverage = PipelineAssessment(
            status="thin",
            headline="Search space coverage is concentrated.",
            detail=(
                f"{search_coverage.unique_families_30d} families in 30d, "
                f"top share {search_coverage.top_family_share_30d:.1%}."
            ),
        )
    else:
        coverage = PipelineAssessment(
            status="critical",
            headline="Search space coverage is too narrow.",
            detail="Recent runs are clustered in very few families.",
        )

    if not meaningful.measurable:
        cadence = PipelineAssessment(
            status="not_measurable",
            headline="Meaningful-result cadence is not measurable yet.",
            detail="Primary quality metric coverage is insufficient for a reliable cadence estimate.",
        )
    elif meaningful.weekly_meaningful_rate >= 1.0:
        cadence = PipelineAssessment(
            status="good",
            headline="Meaningful-result cadence is healthy.",
            detail=f"{meaningful.weekly_meaningful_rate:.2f} meaningful improvements per week (30d baseline).",
        )
    elif meaningful.weekly_meaningful_rate >= 0.25:
        cadence = PipelineAssessment(
            status="thin",
            headline="Meaningful-result cadence is slow.",
            detail=f"{meaningful.weekly_meaningful_rate:.2f} meaningful improvements per week (30d baseline).",
        )
    else:
        cadence = PipelineAssessment(
            status="critical",
            headline="Meaningful-result cadence is stalled.",
            detail=f"{meaningful.weekly_meaningful_rate:.2f} meaningful improvements per week (30d baseline).",
        )

    return TrainingPipelineAssessments(
        concurrent_experiments=concurrent,
        search_space_coverage=coverage,
        meaningful_result_cadence=cadence,
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


def _extract_summary_payload(run: object) -> dict[str, object]:
    try:
        raw_summary = getattr(run, "summary", {})
    except Exception:
        return {}
    if raw_summary is None:
        return {}
    try:
        return dict(raw_summary)
    except Exception:
        return {}


def _fetch_wandb_state_slice(
    *,
    entity: str,
    project: str,
    state: str,
    per_state_limit: int,
    metric_keys: list[str],
) -> list[WandbRunSample]:
    include_full_run_payload = state == "finished"
    wandb = importlib.import_module("wandb")
    api = wandb.Api(timeout=12)
    runs = islice(
        api.runs(
            f"{entity}/{project}",
            filters={"state": state},
            order="-created_at",
            per_page=max(50, min(200, per_state_limit)),
            lazy=not include_full_run_payload,
        ),
        max(1, per_state_limit),
    )
    samples: list[WandbRunSample] = []
    for run in runs:
        created_at = _to_datetime(run.created_at)
        summary_payload = _extract_summary_payload(run) if include_full_run_payload else {}
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


def _discover_repo_root() -> Path:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if (parent / "recipes" / "experiment").is_dir() and (parent / "metta" / "rl").is_dir():
            return parent
    msg = "Could not resolve repository root for training pipeline audit."
    raise RuntimeError(msg)


def _extract_assignment_string(text: str, name: str, *, default: str) -> str:
    pattern = re.compile(_ASSIGNMENT_PATTERN_TEMPLATE.format(name=re.escape(name)), re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        return default
    raw = match.group("value").strip()
    string_match = re.search(r'"([^"]+)"', raw)
    if string_match is not None:
        return string_match.group(1)
    return default


def _extract_assignment_int(text: str, name: str, *, default: int) -> int:
    pattern = re.compile(_ASSIGNMENT_PATTERN_TEMPLATE.format(name=re.escape(name)), re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        return default
    raw = match.group("value").replace("_", "")
    int_match = re.search(r"\b(\d+)\b", raw)
    if int_match is None:
        return default
    return int(int_match.group(1))


def _extract_progress_metric(cogsguard_text: str) -> str:
    match = re.search(r'tt\.stats_reporter\.progress_metric\s*=\s*"([^"]+)"', cogsguard_text)
    if match is None:
        return "env_game/cogs/aligned.junction.held"
    return match.group(1)


def _extract_quoted_identifiers(text: str, *, suffix: str) -> list[str]:
    seen: dict[str, None] = {}
    pattern = re.compile(rf'"([a-zA-Z0-9_]+{re.escape(suffix)})"')
    for match in pattern.finditer(text):
        seen.setdefault(match.group(1), None)
    return list(seen.keys())


@lru_cache(maxsize=1)
def _collect_recipe_loss_keys(*, repo_root: Path) -> list[str]:
    recipe_root = repo_root / "recipes" / "experiment"
    loss_keys: set[str] = {"ppo_actor", "ppo_critic"}
    add_loss_pattern = re.compile(r'add_loss\("([^"]+)"')
    for recipe_path in recipe_root.rglob("*.py"):
        text = recipe_path.read_text(encoding="utf-8")
        for match in add_loss_pattern.finditer(text):
            loss_keys.add(match.group(1))
    return sorted(loss_keys)


@lru_cache(maxsize=1)
def _collect_core_loss_modules(*, repo_root: Path) -> list[str]:
    loss_root = repo_root / "metta" / "rl" / "loss"
    modules = [path.stem for path in loss_root.glob("*.py") if path.stem != "__init__"]
    return sorted(modules)
