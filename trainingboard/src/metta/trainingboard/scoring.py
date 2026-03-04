from __future__ import annotations

import json
from math import prod
from pathlib import Path

from metta.trainingboard.keyword_match import count_keyword_hits, matching_keywords
from metta.trainingboard.models import AxisPanel, AxisSpec, DashboardSnapshot, ImprovementCandidate, ResearchPaperRecord

AXIS_SPECS: list[AxisSpec] = [
    AxisSpec(
        axis_id="experience_parallelism",
        index=1,
        title="Experience-Level Parallelism",
        principle="More experience-level parallelism (more GPUs)",
        prior_multiplier=1.42,
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
        prior_multiplier=1.37,
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
        prior_multiplier=1.34,
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
        prior_multiplier=1.39,
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
        prior_multiplier=1.25,
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
        prior_multiplier=1.22,
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


def load_cached_papers(cache_path: Path) -> list[ResearchPaperRecord]:
    if not cache_path.is_file():
        return []
    raw_records = json.loads(cache_path.read_text(encoding="utf-8"))
    return [ResearchPaperRecord.model_validate(raw_record) for raw_record in raw_records]


def _axis_signals(record: ResearchPaperRecord) -> dict[str, float]:
    text = record.searchable_text()
    recommendation_text = " ".join(record.recommendations).lower()
    signals: dict[str, float] = {}
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


def _build_axis_panel(spec: AxisSpec, papers: list[ResearchPaperRecord]) -> AxisPanel:
    scored_papers: list[tuple[ResearchPaperRecord, float]] = []
    for paper in papers:
        signals = _axis_signals(paper)
        if spec.axis_id not in signals:
            continue
        scored_papers.append((paper, signals[spec.axis_id]))

    scored_papers.sort(key=lambda item: item[1], reverse=True)

    evidence_count = len(scored_papers)
    evidence_mass = sum(score for _, score in scored_papers)
    evidence_boost = 1.0 + min(0.45, evidence_count * 0.03 + evidence_mass * 0.05)
    projected_multiplier = round(spec.prior_multiplier * evidence_boost, 2)
    confidence = round(min(0.95, 0.38 + evidence_count * 0.06 + evidence_mass * 0.04), 2)
    opportunity_score = round((projected_multiplier - 1.0) * confidence, 3)

    evidence_titles = [paper.title for paper, _ in scored_papers[:4]]
    ranked_wins = sorted(spec.wins, key=lambda win: win.expected_multiplier, reverse=True)

    return AxisPanel(
        axis_id=spec.axis_id,
        index=spec.index,
        title=spec.title,
        principle=spec.principle,
        prior_multiplier=spec.prior_multiplier,
        projected_multiplier=projected_multiplier,
        confidence=confidence,
        evidence_count=evidence_count,
        evidence_titles=evidence_titles,
        opportunity_score=opportunity_score,
        best_wins=ranked_wins,
    )


def build_dashboard_snapshot(papers: list[ResearchPaperRecord]) -> DashboardSnapshot:
    panels = [_build_axis_panel(spec, papers) for spec in AXIS_SPECS]
    ranked_panels = sorted(
        panels,
        key=lambda panel: (panel.opportunity_score, panel.projected_multiplier, -panel.index),
        reverse=True,
    )
    combined_multiplier = round(prod(panel.projected_multiplier for panel in ranked_panels), 2)
    return DashboardSnapshot.build(combined_multiplier=combined_multiplier, ranked_axes=ranked_panels)


def build_dashboard_snapshot_from_cache(cache_path: Path) -> DashboardSnapshot:
    return build_dashboard_snapshot(load_cached_papers(cache_path))
