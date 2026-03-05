import os
from pathlib import Path

import metta.trainingboard.local.backend.server as server_module
from metta.trainingboard.local.backend.server import (
    _resolve_frontend_target,
    build_board_payload_for_state_dir,
    build_dashboard_for_state_dir,
    build_task_ranking_for_state_dir,
    cache_path_for_state_dir,
    dashboard_cache_path_for_state_dir,
    default_repo_cache_path,
    parse_args,
    task_ranking_llm_cache_path_for_state_dir,
)
from metta.trainingboard.models import LLMTaskScores, ResearchPaperRecord, TaskExecutionScores


def test_parse_args_defaults() -> None:
    args = parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8877


def test_resolve_frontend_target_blocks_traversal(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir(parents=True)

    assert _resolve_frontend_target(static_root, "../secrets.txt") is None
    assert _resolve_frontend_target(static_root, "../static/app.js") is None
    assert _resolve_frontend_target(static_root, "app.js") == (static_root / "app.js").resolve()


def test_build_dashboard_for_state_dir_works_without_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(server_module, "load_cached_papers", lambda _path: [])
    monkeypatch.setattr(
        server_module,
        "_load_llm_scores_for_state_dir",
        lambda _state_dir: (None, tmp_path / "llm.ndjson"),
    )
    payload = build_dashboard_for_state_dir(tmp_path)
    assert "ranked_axes" in payload
    assert len(payload["ranked_axes"]) == 6
    assert payload["scoring_source"] == "llm_only"
    assert payload["llm_scored_tasks"] == 0
    assert payload["tasks_total"] == 0
    assert payload["llm_coverage"] == 0.0


def test_build_dashboard_for_state_dir_marks_llm_only_when_scores_exist(monkeypatch, tmp_path: Path) -> None:
    paper = ResearchPaperRecord(
        gid="task-1",
        title="Opaque task",
        notes="",
        permalink_url="https://example.com/task-1",
        custom_fields={},
        paper_links=[],
        recommendations=[],
        inferred_axis_scores={},
    )
    llm_scores = LLMTaskScores(
        axis_scores={
            "experience_parallelism": 0.8,
            "experience_quality": 0.0,
            "loss_parallelism": 0.0,
            "loss_signal_quality": 0.0,
            "parameter_parallelism": 0.0,
            "hyperparameter_quality": 0.0,
        },
        execution_scores=TaskExecutionScores(
            simplicity=0.6,
            time_to_implement=0.6,
            failure_likelihood=0.3,
            dependency_load=0.2,
            measurement_speed=0.5,
            reversibility=0.6,
        ),
        evidence_confidence=0.75,
        rationale="",
    )
    monkeypatch.setattr(server_module, "load_cached_papers", lambda _path: [paper])
    monkeypatch.setattr(
        server_module,
        "_load_llm_scores_for_state_dir",
        lambda _state_dir: ({"task-1": llm_scores}, tmp_path / "task_llm_scores.ndjson"),
    )

    payload = build_dashboard_for_state_dir(tmp_path)
    assert payload["scoring_source"] == "llm_only"
    assert payload["llm_scored_tasks"] == 1
    assert payload["tasks_total"] == 1
    assert payload["llm_coverage"] == 1.0


def test_build_task_ranking_for_state_dir_works_without_llm_cache(tmp_path: Path) -> None:
    payload = build_task_ranking_for_state_dir(tmp_path, limit=7)
    assert "ranked_tasks" in payload
    assert len(payload["ranked_tasks"]) <= 7


def test_build_board_payload_for_state_dir_contains_dashboard_and_ranking(tmp_path: Path) -> None:
    payload = build_board_payload_for_state_dir(tmp_path)
    assert "dashboard" in payload
    assert "task_ranking" in payload
    assert len(payload["dashboard"]["ranked_axes"]) == 6
    assert "scoring_source" in payload["dashboard"]
    assert "ranked_tasks" in payload["task_ranking"]


def test_dashboard_cache_path_prefers_newer_cache_between_repo_and_state(monkeypatch, tmp_path: Path) -> None:
    repo_cache_path = tmp_path / "repo_cache.ndjson"
    repo_cache_path.write_text("[]\n", encoding="utf-8")

    state_cache_path = cache_path_for_state_dir(tmp_path)
    state_cache_path.parent.mkdir(parents=True, exist_ok=True)
    state_cache_path.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(server_module, "default_repo_cache_path", lambda _: repo_cache_path)

    os.utime(state_cache_path, (1, 1))
    os.utime(repo_cache_path, (2, 2))
    assert dashboard_cache_path_for_state_dir(tmp_path) == repo_cache_path

    os.utime(state_cache_path, (3, 3))
    assert dashboard_cache_path_for_state_dir(tmp_path) == state_cache_path


def test_dashboard_cache_path_falls_back_to_repo_cache_when_state_missing(monkeypatch, tmp_path: Path) -> None:
    repo_cache_path = tmp_path / "repo_cache.ndjson"
    monkeypatch.setattr(server_module, "default_repo_cache_path", lambda _: repo_cache_path)
    assert dashboard_cache_path_for_state_dir(tmp_path) == repo_cache_path


def test_default_repo_cache_path_falls_back_to_state_cache_when_repo_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(server_module, "_discover_repo_cache_dir", lambda: None)
    assert default_repo_cache_path(tmp_path) == cache_path_for_state_dir(tmp_path)


def test_task_ranking_llm_cache_prefers_newer_between_repo_and_state(monkeypatch, tmp_path: Path) -> None:
    repo_cache_path = tmp_path / "repo_llm_cache.ndjson"
    repo_cache_path.write_text("", encoding="utf-8")

    state_cache_path = cache_path_for_state_dir(tmp_path).parent / "task_llm_scores.ndjson"
    state_cache_path.parent.mkdir(parents=True, exist_ok=True)
    state_cache_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(server_module, "default_repo_llm_cache_path", lambda _: repo_cache_path)
    monkeypatch.setattr(server_module, "llm_cache_path_for_state_dir", lambda _: state_cache_path)

    os.utime(state_cache_path, (1, 1))
    os.utime(repo_cache_path, (2, 2))
    assert task_ranking_llm_cache_path_for_state_dir(tmp_path) == repo_cache_path

    os.utime(state_cache_path, (3, 3))
    assert task_ranking_llm_cache_path_for_state_dir(tmp_path) == state_cache_path
