import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import metta.trainingboard.local.backend.server as server_module
from metta.trainingboard.local.backend.server import (
    _resolve_frontend_target,
    build_board_payload_for_state_dir,
    build_dashboard_for_state_dir,
    build_pipeline_audit_for_state_dir,
    build_pipeline_snapshot_for_state_dir,
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


def test_parse_args_normalizes_base_path() -> None:
    args = parse_args(["--base-path", "/train-board/"])
    assert args.base_path == "/train-board"


def test_parse_args_rejects_relative_base_path() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--base-path", "train-board"])


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


def test_build_board_payload_for_state_dir_contains_dashboard_and_ranking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server_module._pipeline_cache_payload = None
    server_module._pipeline_cache_key = None
    server_module._pipeline_cache_expires_at = 0.0
    server_module._pipeline_audit_cache_payload = None
    server_module._pipeline_audit_cache_expires_at = 0.0
    pipeline_payload = {"available": True, "experiments": {"running_now": 2}}
    monkeypatch.setattr(server_module, "build_pipeline_snapshot_for_state_dir", lambda _state_dir: pipeline_payload)
    monkeypatch.setattr(
        server_module,
        "build_pipeline_audit_for_state_dir",
        lambda _state_dir: {"supports_multi_policy_training": True},
    )
    payload = build_board_payload_for_state_dir(tmp_path)
    assert "dashboard" in payload
    assert "task_ranking" in payload
    assert "pipeline" in payload
    assert "pipeline_audit" in payload
    assert "research_funnel" in payload
    assert len(payload["dashboard"]["ranked_axes"]) == 6
    assert "scoring_source" in payload["dashboard"]
    assert "ranked_tasks" in payload["task_ranking"]
    assert payload["pipeline_audit"]["supports_multi_policy_training"] is True


def test_pipeline_and_funnel_routes_respect_base_path(monkeypatch, tmp_path: Path) -> None:
    pipeline_payload = {"available": True, "experiments": {"running_now": 2}}
    audit_payload = {"supports_multi_policy_training": True}
    funnel_payload = {"tasks_total": 4, "stages": {"paper_selected": 3}}
    monkeypatch.setattr(server_module, "build_pipeline_snapshot_for_state_dir", lambda _state_dir: pipeline_payload)
    monkeypatch.setattr(server_module, "build_pipeline_audit_for_state_dir", lambda _state_dir: audit_payload)
    monkeypatch.setattr(server_module, "build_research_funnel_for_state_dir", lambda _state_dir: funnel_payload)

    class _StubHandler:
        def __init__(self, path: str) -> None:
            self.path = path
            self.server = SimpleNamespace(state_dir=tmp_path, base_path="/train-board")
            self.responses: list[tuple[int, dict]] = []

        def _write_json(self, status_code: int, payload: dict) -> None:
            self.responses.append((status_code, payload))

        def _serve_file(self, _path: Path, _content_type: str) -> None:
            raise AssertionError("unexpected file serving in API route test")

    pipeline_handler = _StubHandler("/train-board/api/v1/pipeline")
    server_module.TrainingBoardHandler.do_GET(pipeline_handler)
    assert pipeline_handler.responses == [(200, pipeline_payload)]

    funnel_handler = _StubHandler("/train-board/api/v1/research-funnel")
    server_module.TrainingBoardHandler.do_GET(funnel_handler)
    assert funnel_handler.responses == [(200, funnel_payload)]

    audit_handler = _StubHandler("/train-board/api/v1/pipeline-audit")
    server_module.TrainingBoardHandler.do_GET(audit_handler)
    assert audit_handler.responses == [(200, audit_payload)]

    off_prefix_handler = _StubHandler("/api/v1/pipeline")
    server_module.TrainingBoardHandler.do_GET(off_prefix_handler)
    assert off_prefix_handler.responses == [(404, {"error": "not found"})]


def test_build_pipeline_audit_for_state_dir_has_canonical_keys(tmp_path: Path) -> None:
    payload = build_pipeline_audit_for_state_dir(tmp_path)
    assert payload["supports_multi_policy_training"] is True
    assert "cogsguard_train_defaults" in payload
    assert "launch_reliability" in payload
    assert "loss_inventory" in payload


def test_pipeline_snapshot_returns_unavailable_when_wandb_fetch_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(server_module.WANDB_ENABLE_ENV, "1")
    monkeypatch.setattr(server_module, "_pipeline_cache_payload", None)
    monkeypatch.setattr(server_module, "_pipeline_cache_key", None)
    monkeypatch.setattr(server_module, "_pipeline_cache_expires_at", 0.0)
    monkeypatch.setattr(
        server_module,
        "fetch_wandb_state_samples",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated wandb failure")),
    )

    payload = build_pipeline_snapshot_for_state_dir(tmp_path)
    assert payload["available"] is False
    assert "Pipeline metrics unavailable" in payload["notes"][0]
    assert "simulated wandb failure" in payload["notes"][0]


def test_pipeline_audit_returns_degraded_payload_when_build_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(server_module, "_pipeline_audit_cache_payload", None)
    monkeypatch.setattr(server_module, "_pipeline_audit_cache_expires_at", 0.0)
    monkeypatch.setattr(
        server_module,
        "build_training_pipeline_audit_snapshot",
        lambda: (_ for _ in ()).throw(RuntimeError("simulated pipeline audit failure")),
    )

    payload = build_pipeline_audit_for_state_dir(tmp_path)
    assert payload["supports_multi_policy_training"] is False
    assert payload["cogsguard_train_defaults"]["command"] == "-"
    assert payload["multi_policy"]["supported"] is False
    assert payload["launch_reliability"]["has_automatic_retry"] is False
    assert "Pipeline audit unavailable" in payload["launch_reliability"]["notes"][0]
    assert "simulated pipeline audit failure" in payload["launch_reliability"]["notes"][0]


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
