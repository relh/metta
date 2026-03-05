from pathlib import Path

from metta.trainingboard.llm_scoring import (
    LLM_RUBRIC_VERSION,
    LLMScoringSummary,
    load_llm_score_cache,
    score_tasks_with_openai,
    write_llm_score_cache,
)
from metta.trainingboard.models import LLMTaskScoreCacheEntry, LLMTaskScores, ResearchPaperRecord, TaskExecutionScores


def _record(gid: str, modified_at: str = "2026-03-04T00:00:00Z") -> ResearchPaperRecord:
    return ResearchPaperRecord(
        gid=gid,
        title=f"Task {gid}",
        notes="",
        permalink_url=f"https://example.com/{gid}",
        created_at="",
        modified_at=modified_at,
        custom_fields={},
        paper_links=[],
        recommendations=[],
        inferred_axis_scores={},
    )


def _llm_scores() -> LLMTaskScores:
    return LLMTaskScores(
        axis_scores={
            "experience_parallelism": 0.5,
            "experience_quality": 0.4,
            "loss_parallelism": 0.3,
            "loss_signal_quality": 0.2,
            "parameter_parallelism": 0.1,
            "hyperparameter_quality": 0.05,
        },
        execution_scores=TaskExecutionScores(
            simplicity=0.6,
            time_to_implement=0.65,
            failure_likelihood=0.2,
            dependency_load=0.25,
            measurement_speed=0.7,
            reversibility=0.75,
        ),
        evidence_confidence=0.8,
        rationale="cached",
    )


def test_score_tasks_with_openai_reuses_cache(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "llm_cache.ndjson"
    model = "gpt-4.1-mini"
    cached = LLMTaskScoreCacheEntry(
        gid="task-1",
        modified_at="2026-03-04T00:00:00Z",
        model=model,
        rubric_version=LLM_RUBRIC_VERSION,
        scored_at="2026-03-04T01:00:00+00:00",
        scores=_llm_scores(),
    )
    write_llm_score_cache(cache_path, {"task-1": cached})

    def fail_if_called(*args, **kwargs) -> LLMTaskScores:  # noqa: ARG001
        raise AssertionError("LLM should not be called when cache entry is valid.")

    monkeypatch.setattr("metta.trainingboard.llm_scoring._score_task_with_openai", fail_if_called)
    scores, summary = score_tasks_with_openai(
        [_record("task-1")],
        model=model,
        api_key="key-1",
        cache_path=cache_path,
        task_limit=1,
        force_refresh=False,
    )

    assert "task-1" in scores
    assert isinstance(summary, LLMScoringSummary)
    assert summary.reused_count == 1
    assert summary.scored_count == 0
    assert summary.task_offset == 0
    assert summary.task_limit == 1


def test_score_tasks_with_openai_writes_new_scores(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "llm_cache.ndjson"

    def fake_score(*args, **kwargs) -> LLMTaskScores:  # noqa: ARG001
        return _llm_scores()

    monkeypatch.setattr("metta.trainingboard.llm_scoring._score_task_with_openai", fake_score)
    scores, summary = score_tasks_with_openai(
        [_record("task-1"), _record("task-2")],
        model="gpt-4.1-mini",
        api_key="key-1",
        cache_path=cache_path,
        task_limit=1,
        force_refresh=False,
    )

    assert list(scores.keys()) == ["task-1"]
    assert summary.processed_count == 1
    assert summary.scored_count == 1
    assert summary.task_offset == 0
    assert summary.task_limit == 1
    reloaded_cache = load_llm_score_cache(cache_path)
    assert "task-1" in reloaded_cache


def test_score_tasks_with_openai_respects_offset(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "llm_cache.ndjson"

    def fake_score(*args, **kwargs) -> LLMTaskScores:  # noqa: ARG001
        return _llm_scores()

    monkeypatch.setattr("metta.trainingboard.llm_scoring._score_task_with_openai", fake_score)
    scores, summary = score_tasks_with_openai(
        [_record("task-1"), _record("task-2"), _record("task-3")],
        model="gpt-4.1-mini",
        api_key="key-1",
        cache_path=cache_path,
        task_limit=1,
        task_offset=1,
        force_refresh=False,
    )

    assert list(scores.keys()) == ["task-2"]
    assert summary.task_offset == 1
    assert summary.task_limit == 1
    assert summary.processed_count == 1
