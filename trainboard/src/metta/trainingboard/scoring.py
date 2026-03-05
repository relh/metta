from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from metta.trainingboard.keyword_match import count_keyword_hits, matching_keywords
from metta.trainingboard.models import (
    AxisId,
    AxisPanel,
    AxisSpec,
    DashboardSnapshot,
    ExecutionMetricId,
    ImprovementCandidate,
    LLMTaskScores,
    RankedTask,
    ResearchPaperRecord,
    TaskExecutionScores,
    TaskRankingSnapshot,
)
from metta.trainingboard.normalized_cache import load_normalized_records

AXIS_SPECS: list[AxisSpec] = [
    AxisSpec(
        axis_id="experience_parallelism",
        index=1,
        title="Experience-Level Parallelism",
        principle="More experience-level parallelism (more GPUs)",
        keywords=["rollout", "actor", "gpu", "parallel", "throughput", "experience generation", "simulation"],
        wins=[
            ImprovementCandidate(
                name="Scale actor pools across idle GPUs",
                summary="Increase environment actor shards and overlap rollout collection with learner updates.",
                expected_multiplier=1.28,
            ),
            ImprovementCandidate(
                name="Asynchronous rollout staging",
                summary="Decouple inference collection from learner commit cadence to cut idle wall-clock gaps.",
                expected_multiplier=1.2,
            ),
            ImprovementCandidate(
                name="Dynamic batch packing for actors",
                summary="Pack variable-length rollouts to reduce tail-latency in generation.",
                expected_multiplier=1.13,
            ),
        ],
    ),
    AxisSpec(
        axis_id="experience_quality",
        index=2,
        title="Experience Quality",
        principle="Better quality experience generation (better curriculum models)",
        keywords=["curriculum", "exploration", "difficulty", "teacher", "sampling", "trajectory", "map selection"],
        wins=[
            ImprovementCandidate(
                name="Adaptive curriculum scheduler",
                summary="Drive scenario selection from regret and competency gaps instead of static phases.",
                expected_multiplier=1.24,
            ),
            ImprovementCandidate(
                name="Failure-mode replay weighting",
                summary="Bias generation toward high-learning-value episodes from recent failures.",
                expected_multiplier=1.17,
            ),
            ImprovementCandidate(
                name="Mission coverage balancing",
                summary="Track under-trained map/role slices and enforce target exposure quotas.",
                expected_multiplier=1.12,
            ),
        ],
    ),
    AxisSpec(
        axis_id="loss_parallelism",
        index=3,
        title="Loss-Level Parallelism",
        principle="More loss-level parallelism (more frequent feedback)",
        keywords=["learner", "gradient", "minibatch", "feedback", "update frequency", "pipeline", "allreduce"],
        wins=[
            ImprovementCandidate(
                name="Higher learner update cadence",
                summary="Increase learner passes per collected step with bounded staleness.",
                expected_multiplier=1.21,
            ),
            ImprovementCandidate(
                name="Micro-batch pipelining",
                summary="Pipeline micro-batches to reduce optimizer idle time and smooth feedback latency.",
                expected_multiplier=1.15,
            ),
            ImprovementCandidate(
                name="Distributed advantage normalization",
                summary="Normalize across shards each step to stabilize more frequent updates.",
                expected_multiplier=1.1,
            ),
        ],
    ),
    AxisSpec(
        axis_id="loss_signal_quality",
        index=4,
        title="Loss Signal Quality",
        principle="Better loss signal (better critic models)",
        keywords=["critic", "value", "advantage", "reward model", "bootstrap", "distributional", "td"],
        wins=[
            ImprovementCandidate(
                name="Distributional critic upgrade",
                summary="Shift to distributional value targets for lower-variance policy gradients.",
                expected_multiplier=1.26,
            ),
            ImprovementCandidate(
                name="Long-horizon return shaping",
                summary="Improve temporal-credit assignment via target decomposition and auxiliary signals.",
                expected_multiplier=1.18,
            ),
            ImprovementCandidate(
                name="Critic calibration sweeps",
                summary="Tune critic architecture and normalization for stable advantages.",
                expected_multiplier=1.12,
            ),
        ],
    ),
    AxisSpec(
        axis_id="parameter_parallelism",
        index=5,
        title="Parameter-Level Parallelism",
        principle="More parameter-level parallelism (bigger base models)",
        keywords=["model size", "parameter", "sharding", "fsdp", "tensor parallel", "moe", "transformer"],
        wins=[
            ImprovementCandidate(
                name="Sharded larger policy backbone",
                summary="Scale model width/depth with parameter sharding and tuned communication overlap.",
                expected_multiplier=1.23,
            ),
            ImprovementCandidate(
                name="MoE policy heads",
                summary="Expand capacity with sparse experts while controlling inference cost.",
                expected_multiplier=1.16,
            ),
            ImprovementCandidate(
                name="Activation checkpoint strategy",
                summary="Trade compute for memory to unlock larger context and larger models.",
                expected_multiplier=1.1,
            ),
        ],
    ),
    AxisSpec(
        axis_id="hyperparameter_quality",
        index=6,
        title="Hyperparameter Quality",
        principle="Better quality hyperparameters (better optimizer models)",
        keywords=["optimizer", "learning rate", "schedule", "entropy", "tuning", "sweep", "pbt"],
        wins=[
            ImprovementCandidate(
                name="Automated schedule search",
                summary="Continuously search LR/entropy/clip schedules over active runs.",
                expected_multiplier=1.2,
            ),
            ImprovementCandidate(
                name="Population-based tuning",
                summary="Exploit-and-explore optimizer settings during training instead of static configs.",
                expected_multiplier=1.15,
            ),
            ImprovementCandidate(
                name="Optimizer-family benchmark harness",
                summary="Compare optimizer families on core missions with wall-clock normalized metrics.",
                expected_multiplier=1.1,
            ),
        ],
    ),
]

EXECUTION_METRICS: list[ExecutionMetricId] = [
    "simplicity",
    "time_to_implement",
    "failure_likelihood",
    "dependency_load",
    "measurement_speed",
    "reversibility",
]

_UNIFORM_AXIS_WEIGHT = 1.0 / len(AXIS_SPECS)
AXIS_IMPACT_WEIGHTS: dict[AxisId, float] = {spec.axis_id: _UNIFORM_AXIS_WEIGHT for spec in AXIS_SPECS}

SIMPLE_POSITIVE_KEYWORDS = [
    "bug fix",
    "small",
    "simple",
    "quick",
    "easy",
    "instrumentation",
    "logging",
    "config",
    "ablation",
    "incremental",
]
SIMPLE_NEGATIVE_KEYWORDS = [
    "distributed",
    "rewrite",
    "migration",
    "from scratch",
    "moe",
    "sharding",
    "large model",
    "new architecture",
    "cross-team",
]
FAST_POSITIVE_KEYWORDS = [
    "quick",
    "short",
    "easy fix",
    "logging",
    "config",
    "small",
    "parameter sweep",
]
FAST_NEGATIVE_KEYWORDS = [
    "rewrite",
    "migration",
    "from scratch",
    "large model",
    "distributed",
    "infrastructure",
    "new architecture",
]
RISK_POSITIVE_KEYWORDS = [
    "novel",
    "unknown",
    "unclear",
    "research",
    "unproven",
    "from scratch",
    "distributed",
    "new architecture",
    "moe",
]
RISK_NEGATIVE_KEYWORDS = [
    "bug fix",
    "proven",
    "incremental",
    "existing",
    "logging",
    "instrumentation",
]
DEPENDENCY_HIGH_KEYWORDS = [
    "integration",
    "api",
    "service",
    "backend",
    "frontend",
    "wandb",
    "asana",
    "kubernetes",
    "docker",
    "database",
    "cross-team",
    "distributed",
]
DEPENDENCY_LOW_KEYWORDS = [
    "single file",
    "local",
    "standalone",
    "script",
    "config",
    "trainer only",
]
MEASUREMENT_FAST_KEYWORDS = [
    "metric",
    "metrics",
    "benchmark",
    "eval",
    "evaluation",
    "logging",
    "throughput",
    "wall-clock",
    "sps",
    "dashboard",
]
MEASUREMENT_SLOW_KEYWORDS = [
    "long horizon",
    "long-term",
    "foundational",
    "future work",
    "open question",
]
REVERSIBLE_POSITIVE_KEYWORDS = [
    "config",
    "flag",
    "toggle",
    "ablation",
    "optional",
    "experiment",
]
REVERSIBLE_NEGATIVE_KEYWORDS = [
    "migration",
    "schema",
    "checkpoint format",
    "api change",
    "rewrite",
    "irreversible",
]

DEDUP_TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
    "w",
    "task",
    "tasks",
    "paper",
    "research",
    "experiment",
    "experiments",
    "try",
    "testing",
    "test",
    "run",
    "runs",
    "implement",
    "implementation",
    "replicate",
}
TITLE_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def load_cached_papers(cache_path: Path) -> list[ResearchPaperRecord]:
    return load_normalized_records(cache_path)


def _axis_signals(record: ResearchPaperRecord) -> dict[AxisId, float]:
    text = record.searchable_text()
    recommendation_text = " ".join(record.recommendations).lower()
    signals: dict[AxisId, float] = {}
    for spec in AXIS_SPECS:
        hits = matching_keywords(text, spec.keywords)
        keyword_signal = min(1.0, 0.18 + 0.14 * len(hits)) if hits else 0.0
        inferred_signal = 0.0
        if spec.axis_id in record.inferred_axis_scores:
            inferred_signal = record.inferred_axis_scores[spec.axis_id]
        recommendation_hits = count_keyword_hits(recommendation_text, spec.keywords)
        recommendation_signal = min(0.24, recommendation_hits * 0.06)
        link_signal = min(0.12, len(record.paper_links) * 0.03)

        base_signal = max(keyword_signal, inferred_signal)
        if base_signal <= 0:
            continue
        signals[spec.axis_id] = min(1.0, base_signal + recommendation_signal + link_signal)
    return signals


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _execution_text(record: ResearchPaperRecord) -> str:
    custom_field_text = "\n".join(f"{key} {value}" for key, value in record.custom_fields.items())
    recommendation_text = "\n".join(record.recommendations)
    return f"{record.title}\n{record.notes}\n{custom_field_text}\n{recommendation_text}".lower()


def _complexity_adjustment(record: ResearchPaperRecord) -> float:
    complexity_text = " ".join(
        value.lower() for key, value in record.custom_fields.items() if "complexity" in key.lower()
    )
    if not complexity_text:
        return 0.0
    if count_keyword_hits(complexity_text, ["very high", "high", "hard", "advanced", "complex"]) > 0:
        return -0.18
    if count_keyword_hits(complexity_text, ["intermediate", "medium", "moderate"]) > 0:
        return -0.06
    if count_keyword_hits(complexity_text, ["low", "easy", "simple"]) > 0:
        return 0.16
    return 0.0


def _score_execution_metrics(record: ResearchPaperRecord) -> TaskExecutionScores:
    text = _execution_text(record)
    complexity_adjustment = _complexity_adjustment(record)

    simple_hits = count_keyword_hits(text, SIMPLE_POSITIVE_KEYWORDS)
    complex_hits = count_keyword_hits(text, SIMPLE_NEGATIVE_KEYWORDS)
    fast_hits = count_keyword_hits(text, FAST_POSITIVE_KEYWORDS)
    slow_hits = count_keyword_hits(text, FAST_NEGATIVE_KEYWORDS)
    risk_hits = count_keyword_hits(text, RISK_POSITIVE_KEYWORDS)
    risk_reducers = count_keyword_hits(text, RISK_NEGATIVE_KEYWORDS)
    dependency_hits = count_keyword_hits(text, DEPENDENCY_HIGH_KEYWORDS)
    dependency_reducers = count_keyword_hits(text, DEPENDENCY_LOW_KEYWORDS)
    measurement_hits = count_keyword_hits(text, MEASUREMENT_FAST_KEYWORDS)
    measurement_slow_hits = count_keyword_hits(text, MEASUREMENT_SLOW_KEYWORDS)
    reversible_hits = count_keyword_hits(text, REVERSIBLE_POSITIVE_KEYWORDS)
    irreversible_hits = count_keyword_hits(text, REVERSIBLE_NEGATIVE_KEYWORDS)

    simplicity = _bounded(0.52 + simple_hits * 0.09 - complex_hits * 0.1 + complexity_adjustment)
    time_to_implement = _bounded(0.5 + fast_hits * 0.1 - slow_hits * 0.1 + complexity_adjustment * 0.75)
    failure_likelihood = _bounded(
        0.34 + risk_hits * 0.1 + max(0.0, -complexity_adjustment) * 0.4 - risk_reducers * 0.09 - simple_hits * 0.04
    )
    dependency_load = _bounded(0.28 + dependency_hits * 0.08 - dependency_reducers * 0.08 + complex_hits * 0.04)
    measurement_speed = _bounded(0.44 + measurement_hits * 0.09 - measurement_slow_hits * 0.08 + simple_hits * 0.03)
    reversibility = _bounded(0.48 + reversible_hits * 0.09 - irreversible_hits * 0.1 - dependency_hits * 0.03)

    return TaskExecutionScores(
        simplicity=simplicity,
        time_to_implement=time_to_implement,
        failure_likelihood=failure_likelihood,
        dependency_load=dependency_load,
        measurement_speed=measurement_speed,
        reversibility=reversibility,
    )


def _task_axis_scores(record: ResearchPaperRecord) -> dict[AxisId, float]:
    signals = _axis_signals(record)
    axis_scores: dict[AxisId, float] = {}
    for spec in AXIS_SPECS:
        if spec.axis_id in signals:
            axis_scores[spec.axis_id] = round(signals[spec.axis_id], 3)
        else:
            axis_scores[spec.axis_id] = 0.0
    return axis_scores


def _task_impact_score(axis_scores: dict[AxisId, float]) -> float:
    return _bounded(sum(axis_scores[spec.axis_id] * AXIS_IMPACT_WEIGHTS[spec.axis_id] for spec in AXIS_SPECS))


def _task_feasibility_score(execution_scores: TaskExecutionScores) -> float:
    success_likelihood = 1.0 - execution_scores.failure_likelihood
    low_dependency_load = 1.0 - execution_scores.dependency_load
    return _bounded(
        execution_scores.simplicity * 0.22
        + execution_scores.time_to_implement * 0.22
        + success_likelihood * 0.24
        + low_dependency_load * 0.12
        + execution_scores.measurement_speed * 0.12
        + execution_scores.reversibility * 0.08
    )


def _task_evidence_confidence(record: ResearchPaperRecord, axis_scores: dict[AxisId, float]) -> float:
    axis_coverage = sum(1 for score in axis_scores.values() if score > 0.0)
    return _bounded(0.42 + axis_coverage * 0.06 + len(record.paper_links) * 0.05 + len(record.recommendations) * 0.03)


def _task_priority_score(impact_score: float, feasibility_score: float, evidence_confidence: float) -> float:
    return _bounded((impact_score * 0.65 + feasibility_score * 0.35) * evidence_confidence)


def _build_ranked_task(record: ResearchPaperRecord, llm_scores: Optional[LLMTaskScores] = None) -> RankedTask:
    if llm_scores is None:
        axis_scores = _task_axis_scores(record)
        execution_scores = _score_execution_metrics(record)
        evidence_confidence = _task_evidence_confidence(record, axis_scores)
    else:
        axis_scores = {spec.axis_id: round(llm_scores.axis_scores[spec.axis_id], 3) for spec in AXIS_SPECS}
        execution_scores = llm_scores.execution_scores
        evidence_confidence = _bounded(llm_scores.evidence_confidence)

    impact_score = _task_impact_score(axis_scores)
    feasibility_score = _task_feasibility_score(execution_scores)
    priority_score = _task_priority_score(impact_score, feasibility_score, evidence_confidence)
    top_axes = [
        axis_id for axis_id, score in sorted(axis_scores.items(), key=lambda item: item[1], reverse=True) if score > 0.0
    ][:2]

    return RankedTask(
        gid=record.gid,
        title=record.title,
        permalink_url=record.permalink_url,
        axis_scores=axis_scores,
        execution_scores=execution_scores,
        impact_score=impact_score,
        feasibility_score=feasibility_score,
        evidence_confidence=evidence_confidence,
        priority_score=priority_score,
        top_axes=top_axes,
    )


def _dedupe_title_key(title: str, gid: str) -> str:
    normalized = title.strip().lower()
    if not normalized:
        return f"gid:{gid}"
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized.split("?", 1)[0]
    tokens = TITLE_TOKEN_PATTERN.findall(normalized)
    if not tokens:
        return normalized
    filtered_tokens = [token for token in tokens if token not in DEDUP_TITLE_STOPWORDS]
    key_tokens = filtered_tokens if filtered_tokens else tokens
    return " ".join(key_tokens[:6])


def _dedupe_ranked_tasks(ranked_tasks: list[RankedTask]) -> list[RankedTask]:
    deduped: list[RankedTask] = []
    seen_keys: set[str] = set()
    for task in ranked_tasks:
        key = _dedupe_title_key(task.title, task.gid)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(task)
    return deduped


def _axis_signal_for_dashboard(
    record: ResearchPaperRecord,
    axis_id: AxisId,
    llm_scores_by_gid: Optional[dict[str, LLMTaskScores]],
) -> float:
    if llm_scores_by_gid is None:
        return _axis_signals(record).get(axis_id, 0.0)
    if record.gid not in llm_scores_by_gid:
        return 0.0
    return _bounded(llm_scores_by_gid[record.gid].axis_scores[axis_id])


def _build_axis_panel(
    spec: AxisSpec,
    papers: list[ResearchPaperRecord],
    llm_scores_by_gid: Optional[dict[str, LLMTaskScores]] = None,
) -> AxisPanel:
    scored_papers: list[tuple[ResearchPaperRecord, float]] = []
    for paper in papers:
        signal = _axis_signal_for_dashboard(paper, spec.axis_id, llm_scores_by_gid)
        if signal <= 0.0:
            continue
        scored_papers.append((paper, signal))

    scored_papers.sort(key=lambda item: item[1], reverse=True)

    evidence_count = len(scored_papers)
    evidence_mass = sum(score for _, score in scored_papers)
    confidence = round(min(0.95, evidence_count / max(1, len(papers))), 2)
    mean_axis_score = 0.0 if evidence_count == 0 else evidence_mass / evidence_count
    opportunity_score = round(mean_axis_score * confidence, 3)

    evidence_titles = [paper.title for paper, _ in scored_papers[:4]]
    ranked_wins = sorted(spec.wins, key=lambda win: win.expected_multiplier, reverse=True)

    return AxisPanel(
        axis_id=spec.axis_id,
        index=spec.index,
        title=spec.title,
        principle=spec.principle,
        confidence=confidence,
        evidence_count=evidence_count,
        evidence_titles=evidence_titles,
        opportunity_score=opportunity_score,
        best_wins=ranked_wins,
    )


def build_dashboard_snapshot(
    papers: list[ResearchPaperRecord],
    llm_scores_by_gid: Optional[dict[str, LLMTaskScores]] = None,
) -> DashboardSnapshot:
    panels = [_build_axis_panel(spec, papers, llm_scores_by_gid=llm_scores_by_gid) for spec in AXIS_SPECS]
    # Keep board order stable at axes 1..6 for wall-screen readability.
    return DashboardSnapshot.build(ranked_axes=panels)


def build_dashboard_snapshot_from_cache(
    cache_path: Path,
    llm_scores_by_gid: Optional[dict[str, LLMTaskScores]] = None,
) -> DashboardSnapshot:
    return build_dashboard_snapshot(load_cached_papers(cache_path), llm_scores_by_gid=llm_scores_by_gid)


def build_task_ranking_snapshot(
    papers: list[ResearchPaperRecord],
    limit: Optional[int] = 50,
    llm_scores_by_gid: Optional[dict[str, LLMTaskScores]] = None,
    dedupe_titles: bool = True,
    require_llm_scores: bool = False,
) -> TaskRankingSnapshot:
    ranked_tasks: list[RankedTask] = []
    for paper in papers:
        llm_scores = None if llm_scores_by_gid is None else llm_scores_by_gid.get(paper.gid)
        if require_llm_scores and llm_scores is None:
            continue
        ranked_tasks.append(_build_ranked_task(paper, llm_scores=llm_scores))
    ranked_tasks = sorted(
        ranked_tasks,
        key=lambda task: (
            task.priority_score,
            task.impact_score,
            task.feasibility_score,
            task.evidence_confidence,
            task.gid,
        ),
        reverse=True,
    )
    if dedupe_titles:
        ranked_tasks = _dedupe_ranked_tasks(ranked_tasks)
    if limit is not None:
        ranked_tasks = ranked_tasks[: max(0, limit)]

    return TaskRankingSnapshot.build(
        tasks_scored=len(ranked_tasks) if require_llm_scores else len(papers),
        impact_metrics=[spec.axis_id for spec in AXIS_SPECS],
        execution_metrics=EXECUTION_METRICS,
        ranked_tasks=ranked_tasks,
    )


def build_task_leaderboards(
    ranked_tasks: list[RankedTask], top_n: int = 10
) -> dict[str, list[RankedTask] | dict[AxisId, list[RankedTask]]]:
    capped_top_n = max(0, top_n)
    top_overall = ranked_tasks[:capped_top_n]
    top_by_axis: dict[AxisId, list[RankedTask]] = {}
    for spec in AXIS_SPECS:
        axis_id = spec.axis_id
        axis_tasks = [task for task in ranked_tasks if task.axis_scores[axis_id] > 0.0]
        axis_tasks.sort(
            key=lambda task: (
                task.axis_scores[axis_id],
                task.priority_score,
                task.impact_score,
                task.feasibility_score,
                task.gid,
            ),
            reverse=True,
        )
        top_by_axis[axis_id] = axis_tasks[:capped_top_n]
    return {"top_overall": top_overall, "top_by_axis": top_by_axis}


def build_task_ranking_snapshot_from_cache(
    cache_path: Path,
    limit: Optional[int] = 50,
    llm_scores_by_gid: Optional[dict[str, LLMTaskScores]] = None,
    dedupe_titles: bool = True,
    require_llm_scores: bool = False,
) -> TaskRankingSnapshot:
    return build_task_ranking_snapshot(
        load_cached_papers(cache_path),
        limit=limit,
        llm_scores_by_gid=llm_scores_by_gid,
        dedupe_titles=dedupe_titles,
        require_llm_scores=require_llm_scores,
    )
