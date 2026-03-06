from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from metta.trainingboard.models import LLMTaskScores, ResearchPaperRecord, TaskExecutionScores
from metta.trainingboard.pipeline_metrics import (
    WandbRunSample,
    _extract_assignment_int,
    build_research_funnel_snapshot,
    build_training_pipeline_snapshot_from_samples,
    fetch_wandb_state_samples,
)


def test_research_funnel_snapshot_tracks_paper_repo_impl_stages() -> None:
    papers = [
        ResearchPaperRecord(
            gid="task-paper-only",
            title="Paper only",
            notes="",
            permalink_url="https://example.com/1",
            custom_fields={"Implementation Status": "Not Started"},
            paper_links=["https://arxiv.org/abs/1111.11111"],
            recommendations=[],
            inferred_axis_scores={},
        ),
        ResearchPaperRecord(
            gid="task-paper-repo",
            title="Paper + repo",
            notes="Author repo https://github.com/org/repo",
            permalink_url="https://example.com/2",
            custom_fields={"Implementation Status": "In Progress"},
            paper_links=["https://openreview.net/forum?id=abc"],
            recommendations=[],
            inferred_axis_scores={},
        ),
        ResearchPaperRecord(
            gid="task-paper-repo-done",
            title="Paper + repo + done",
            notes="https://github.com/org/repo2",
            permalink_url="https://example.com/3",
            custom_fields={"Implementation Status": "Completed"},
            paper_links=["https://arxiv.org/abs/2222.22222"],
            recommendations=[],
            inferred_axis_scores={},
        ),
    ]
    llm_scores = {
        "task-paper-only": LLMTaskScores(
            axis_scores={
                "experience_parallelism": 0.8,
                "experience_quality": 0.2,
                "loss_parallelism": 0.1,
                "loss_signal_quality": 0.1,
                "parameter_parallelism": 0.05,
                "hyperparameter_quality": 0.1,
            },
            execution_scores=TaskExecutionScores(
                simplicity=0.8,
                time_to_implement=0.7,
                failure_likelihood=0.2,
                dependency_load=0.3,
                measurement_speed=0.6,
                reversibility=0.8,
            ),
            evidence_confidence=0.6,
            rationale="",
        )
    }

    snapshot = build_research_funnel_snapshot(papers, llm_scores_by_gid=llm_scores)

    assert snapshot.tasks_total == 3
    assert snapshot.llm_scored_tasks == 1
    assert snapshot.paper_signal_tasks == 3
    assert snapshot.repo_signal_tasks == 2
    assert snapshot.implemented_tasks == 1
    assert snapshot.paper_repo_tasks == 2
    assert snapshot.paper_repo_implemented_tasks == 1
    assert snapshot.stages.paper_selected == 3
    assert snapshot.stages.author_repo_found == 2
    assert snapshot.stages.implemented_in_metta == 1
    assert snapshot.stages.paper_to_repo_conversion == 0.667
    assert snapshot.stages.repo_to_impl_conversion == 0.5


def test_training_pipeline_snapshot_computes_concurrency_and_meaningful_rate() -> None:
    now = datetime(2026, 3, 5, 17, 0, tzinfo=UTC)
    finished_samples = [
        WandbRunSample(
            run_id=f"run-finished-{index}",
            display_name=f"alpha.exp.{index + 2}",
            state="finished",
            created_at=now - timedelta(days=7 - index),
            summary_metrics={"env_collective/cogs/aligned.junction.held": value},
        )
        for index, value in enumerate([0.31, 0.32, 0.33, 0.35, 0.36, 0.37, 0.39, 0.5])
    ]
    samples = [
        WandbRunSample(
            run_id="run-running-recent",
            display_name="alpha.exp.1",
            state="running",
            created_at=datetime(2026, 3, 4, 17, 0, tzinfo=UTC),
            summary_metrics={},
        ),
        WandbRunSample(
            run_id="run-running-stale",
            display_name="beta.exp.1",
            state="running",
            created_at=datetime(2026, 2, 10, 17, 0, tzinfo=UTC),
            summary_metrics={},
        ),
        *finished_samples,
        WandbRunSample(
            run_id="run-crashed-1",
            display_name="gamma.exp.1",
            state="crashed",
            created_at=datetime(2026, 3, 2, 17, 0, tzinfo=UTC),
            summary_metrics={},
        ),
    ]

    snapshot = build_training_pipeline_snapshot_from_samples(samples, now_utc=now)

    assert snapshot.available is True
    assert snapshot.experiments.running_now == 2
    assert snapshot.experiments.running_recent_7d == 1
    assert snapshot.experiments.running_stale_gt_14d == 1
    assert snapshot.experiments.finished_recent_7d == 8
    assert snapshot.experiments.crashed_recent_7d == 1
    assert snapshot.experiments.starts_recent_7d_lower_bound == 10
    assert snapshot.experiments.crash_rate_recent_7d == 0.111
    assert snapshot.search_coverage.unique_families_30d == 3
    assert snapshot.meaningful_results.primary_metric == "env_collective/cogs/aligned.junction.held"
    assert snapshot.meaningful_results.measurable is True
    assert snapshot.meaningful_results.meaningful_events_7d >= 2
    assert snapshot.assessments.concurrent_experiments.status in {"good", "thin"}
    assert snapshot.assessments.search_space_coverage.status in {"good", "thin"}
    assert snapshot.assessments.meaningful_result_cadence.status in {"good", "thin"}


def test_training_pipeline_snapshot_leaves_primary_metric_empty_when_unlogged() -> None:
    now = datetime(2026, 3, 5, 17, 0, tzinfo=UTC)
    samples = [
        WandbRunSample(
            run_id=f"run-finished-{index}",
            display_name=f"family.exp.{index}",
            state="finished",
            created_at=now - timedelta(days=index),
            summary_metrics={},
        )
        for index in range(10)
    ]

    snapshot = build_training_pipeline_snapshot_from_samples(samples, now_utc=now)

    assert snapshot.meaningful_results.primary_metric == ""
    assert snapshot.meaningful_results.primary_metric_coverage_ratio == 0.0
    assert snapshot.meaningful_results.measurable is False
    assert snapshot.assessments.meaningful_result_cadence.status == "not_measurable"


def test_fetch_wandb_state_samples_skips_broken_summary_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenSummaryRun:
        id = "broken-run"
        name = "broken-run"
        display_name = "broken-run"
        created_at = "2026-03-06T00:00:00+00:00"
        tags: list[str] = []

        @property
        def summary(self) -> dict[str, float]:
            msg = "summary unavailable"
            raise ValueError(msg)

    class _Api:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        def runs(
            self,
            _path: str,
            *,
            filters: dict[str, str],
            order: str,
            per_page: int,
            lazy: bool,
        ) -> list[_BrokenSummaryRun]:
            assert filters["state"] in {"running", "finished", "crashed"}
            assert order == "-created_at"
            assert per_page >= 50
            if filters["state"] == "finished":
                assert lazy is False
            else:
                assert lazy is True
            return [_BrokenSummaryRun()]

    class _WandbModule:
        Api = _Api

    monkeypatch.setattr("importlib.import_module", lambda _name: _WandbModule())
    samples = fetch_wandb_state_samples(entity="metta-research", project="metta", per_state_limit=5)

    assert len(samples) == 3
    assert all(sample.run_id == "broken-run" for sample in samples)
    assert all(sample.summary_metrics == {} for sample in samples)


def test_extract_assignment_int_allows_whitespace_around_equals() -> None:
    module_text = "\n".join(
        [
            "DEFAULT_NUM_AGENTS = 8",
            "DEFAULT_MAX_STEPS: int = 10_000",
        ]
    )

    assert _extract_assignment_int(module_text, "DEFAULT_NUM_AGENTS", default=1) == 8
    assert _extract_assignment_int(module_text, "DEFAULT_MAX_STEPS", default=1) == 10000
