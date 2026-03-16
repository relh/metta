from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import metta.trainingboard.cli as cli_module
from metta.trainingboard.cli import main
from metta.trainingboard.models import ResearchPaperRecord


def test_cli_help_lists_expected_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "ingest-asana" in result.output
    assert "snapshot" in result.output
    assert "rank-tasks" in result.output


def test_ingest_asana_defaults_to_repo_output(monkeypatch, tmp_path: Path) -> None:
    captured_paths: dict[str, Path] = {}

    def fake_sync_project_research(**kwargs):
        captured_paths["output_path"] = kwargs["output_path"]
        captured_paths["raw_cache_path"] = kwargs["raw_cache_path"]
        return [], SimpleNamespace(
            source_key="project-1:all",
            used_project_fallback=False,
            output_records_total=0,
            records_written=0,
            story_reuse_count=0,
            story_refetch_count=0,
            tasks_total=0,
            paper_link_count=0,
            recommendation_count=0,
        )

    monkeypatch.setattr(cli_module, "sync_project_research", fake_sync_project_research)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ingest-asana",
            "--project-gid",
            "project-1",
            "--token",
            "token-1",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured_paths["output_path"] == cli_module.default_repo_cache_path(tmp_path)
    assert captured_paths["raw_cache_path"] == cli_module.default_raw_cache_path(tmp_path, "project-1", None)


def test_ingest_asana_no_repo_output_uses_state_cache(monkeypatch, tmp_path: Path) -> None:
    captured_paths: dict[str, Path] = {}

    def fake_sync_project_research(**kwargs):
        captured_paths["output_path"] = kwargs["output_path"]
        return [], SimpleNamespace(
            source_key="project-1:all",
            used_project_fallback=False,
            output_records_total=0,
            records_written=0,
            story_reuse_count=0,
            story_refetch_count=0,
            tasks_total=0,
            paper_link_count=0,
            recommendation_count=0,
        )

    monkeypatch.setattr(cli_module, "sync_project_research", fake_sync_project_research)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ingest-asana",
            "--project-gid",
            "project-1",
            "--token",
            "token-1",
            "--no-repo-output",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured_paths["output_path"] == cli_module.cache_path_for_state_dir(tmp_path)


def test_rank_tasks_uses_cache_and_prints_json(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeTaskRankingSnapshot:
        def model_dump(self) -> dict[str, object]:
            return {"tasks_scored": 3, "ranked_tasks": [{"gid": "task-1"}]}

    def fake_dashboard_cache_path_for_state_dir(state_dir: Path) -> Path:
        captured["state_dir"] = state_dir
        return tmp_path / "cache.ndjson"

    def fake_load_normalized_records(cache_path: Path) -> list[ResearchPaperRecord]:
        captured["cache_path"] = cache_path
        return []

    def fake_task_ranking_llm_cache_path_for_state_dir(state_dir: Path) -> Path:
        captured["llm_state_dir"] = state_dir
        return tmp_path / "llm-cache.ndjson"

    def fake_load_llm_score_cache(cache_path: Path) -> dict[str, object]:
        captured["llm_cache_path"] = cache_path
        return {"task-1": SimpleNamespace(scores="llm-score")}

    def fake_build_task_ranking_snapshot(
        papers: list[ResearchPaperRecord],
        limit: int,
        llm_scores_by_gid: object,
        require_llm_scores: bool,
    ) -> FakeTaskRankingSnapshot:
        captured["papers"] = papers
        captured["limit"] = limit
        captured["llm_scores_by_gid"] = llm_scores_by_gid
        captured["require_llm_scores"] = require_llm_scores
        return FakeTaskRankingSnapshot()

    monkeypatch.setattr(cli_module, "dashboard_cache_path_for_state_dir", fake_dashboard_cache_path_for_state_dir)
    monkeypatch.setattr(
        cli_module, "task_ranking_llm_cache_path_for_state_dir", fake_task_ranking_llm_cache_path_for_state_dir
    )
    monkeypatch.setattr(cli_module, "load_normalized_records", fake_load_normalized_records)
    monkeypatch.setattr(cli_module, "load_llm_score_cache", fake_load_llm_score_cache)
    monkeypatch.setattr(cli_module, "build_task_ranking_snapshot", fake_build_task_ranking_snapshot)

    runner = CliRunner()
    result = runner.invoke(main, ["rank-tasks", "--state-dir", str(tmp_path), "--limit", "7"])

    assert result.exit_code == 0
    assert captured["state_dir"] == tmp_path
    assert captured["cache_path"] == tmp_path / "cache.ndjson"
    assert captured["papers"] == []
    assert captured["limit"] == 7
    assert captured["llm_cache_path"] == tmp_path / "llm-cache.ndjson"
    assert captured["llm_scores_by_gid"] == {"task-1": "llm-score"}
    assert captured["require_llm_scores"] is True
    assert '"tasks_scored": 3' in result.output


def test_rank_tasks_rejects_negative_limit() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["rank-tasks", "--limit", "-1"])
    assert result.exit_code != 0
    assert "--limit must be non-negative." in result.output


def test_rank_tasks_rejects_negative_llm_task_limit() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["rank-tasks", "--llm-task-limit", "-3"])
    assert result.exit_code != 0
    assert "--llm-task-limit must be non-negative." in result.output


def test_rank_tasks_rejects_negative_llm_task_offset() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["rank-tasks", "--llm-task-offset", "-2"])
    assert result.exit_code != 0
    assert "--llm-task-offset must be non-negative." in result.output


def test_rank_tasks_llm_mode_uses_llm_scores(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeTaskRankingSnapshot:
        def model_dump(self) -> dict[str, object]:
            return {"tasks_scored": 1, "ranked_tasks": [{"gid": "task-1"}]}

    class FakeSummary:
        def model_dump(self) -> dict[str, object]:
            return {
                "processed_count": 1,
                "scored_count": 1,
                "reused_count": 0,
                "task_offset": 0,
                "task_limit": 1,
            }

    records = [
        ResearchPaperRecord(
            gid="task-1",
            title="Task one",
            notes="",
            permalink_url="https://example.com/task-1",
            custom_fields={},
            paper_links=[],
            recommendations=[],
            inferred_axis_scores={},
        )
    ]

    def fake_dashboard_cache_path_for_state_dir(state_dir: Path) -> Path:
        captured["state_dir"] = state_dir
        return tmp_path / "tasks.ndjson"

    def fake_load_normalized_records(cache_path: Path) -> list[ResearchPaperRecord]:
        captured["cache_path"] = cache_path
        return records

    def fake_resolve_openai_api_key(*, explicit_key: str, token_env: str) -> str:
        captured["explicit_key"] = explicit_key
        captured["token_env"] = token_env
        return "key-123"

    def fake_task_ranking_llm_cache_path_for_state_dir(state_dir: Path) -> Path:
        captured["llm_state_dir"] = state_dir
        return tmp_path / "llm-cache.ndjson"

    def fake_load_llm_score_cache(cache_path: Path) -> dict[str, object]:
        captured["loaded_cache_path"] = cache_path
        return {"task-1": SimpleNamespace(scores="cached-llm-score")}

    def fake_score_tasks_with_openai(
        papers: list[ResearchPaperRecord],
        *,
        model: str,
        api_key: str,
        cache_path: Path,
        task_limit: int | None,
        task_offset: int,
        force_refresh: bool,
    ) -> tuple[dict[str, object], FakeSummary]:
        captured["llm_papers"] = papers
        captured["llm_model"] = model
        captured["llm_api_key"] = api_key
        captured["llm_cache_path"] = cache_path
        captured["llm_task_limit"] = task_limit
        captured["llm_task_offset"] = task_offset
        captured["llm_force_refresh"] = force_refresh
        return {"task-1": object()}, FakeSummary()

    def fake_build_task_ranking_snapshot(
        papers: list[ResearchPaperRecord],
        limit: int,
        llm_scores_by_gid: dict[str, object] | None,
        require_llm_scores: bool,
    ) -> FakeTaskRankingSnapshot:
        captured["build_papers"] = papers
        captured["build_limit"] = limit
        captured["build_llm_scores"] = llm_scores_by_gid
        captured["build_require_llm_scores"] = require_llm_scores
        return FakeTaskRankingSnapshot()

    monkeypatch.setattr(cli_module, "dashboard_cache_path_for_state_dir", fake_dashboard_cache_path_for_state_dir)
    monkeypatch.setattr(cli_module, "load_normalized_records", fake_load_normalized_records)
    monkeypatch.setattr(cli_module, "resolve_openai_api_key", fake_resolve_openai_api_key)
    monkeypatch.setattr(
        cli_module, "task_ranking_llm_cache_path_for_state_dir", fake_task_ranking_llm_cache_path_for_state_dir
    )
    monkeypatch.setattr(cli_module, "load_llm_score_cache", fake_load_llm_score_cache)
    monkeypatch.setattr(cli_module, "score_tasks_with_openai", fake_score_tasks_with_openai)
    monkeypatch.setattr(cli_module, "build_task_ranking_snapshot", fake_build_task_ranking_snapshot)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "rank-tasks",
            "--state-dir",
            str(tmp_path),
            "--limit",
            "5",
            "--llm",
            "--llm-model",
            "gpt-4.1-mini",
            "--llm-task-limit",
            "1",
            "--llm-task-offset",
            "5",
            "--llm-force-refresh",
        ],
    )

    assert result.exit_code == 0
    assert captured["llm_papers"] == records
    assert captured["llm_model"] == "gpt-4.1-mini"
    assert captured["llm_api_key"] == "key-123"
    assert captured["llm_cache_path"] == tmp_path / "llm-cache.ndjson"
    assert captured["loaded_cache_path"] == tmp_path / "llm-cache.ndjson"
    assert captured["llm_task_limit"] == 1
    assert captured["llm_task_offset"] == 5
    assert captured["llm_force_refresh"] is True
    assert captured["build_llm_scores"] == {"task-1": "cached-llm-score"}
    assert captured["build_require_llm_scores"] is True
    assert '"llm_summary"' in result.output
