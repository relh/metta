import json

from metta.trainingboard.ingest import asana as asana_ingest
from metta.trainingboard.ingest.asana import (
    RawAsanaCustomField,
    RawAsanaStory,
    RawAsanaTask,
    default_raw_cache_path,
    parse_project_and_section_from_url,
    sync_project_research,
)


def _read_ndjson(path) -> list[dict]:
    records: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def test_parse_project_and_section_from_url() -> None:
    project_gid, section_gid = parse_project_and_section_from_url(
        "https://app.asana.com/1/1209016784099267/project/1209041170403490/list/1209017020013677"
    )
    assert project_gid == "1209041170403490"
    assert section_gid == "1209017020013677"


def test_default_raw_cache_path_uses_project_and_section(tmp_path) -> None:
    path = default_raw_cache_path(tmp_path, "1209041170403490", "1209017020013677")
    assert path.name == "asana_research_raw_cache_1209041170403490_1209017020013677.json"


def test_extractors_find_research_links_and_recommendations() -> None:
    chunks = [
        "Read https://arxiv.org/abs/1234.5678 and https://openreview.net/forum?id=abc",
        "Recommendation: we should improve critic value calibration and increase learner update frequency.",
    ]

    paper_links = asana_ingest.extract_paper_links(chunks)
    recommendations = asana_ingest.extract_recommendations(chunks)
    axis_scores = asana_ingest.infer_axis_scores("\n".join(chunks), recommendations, paper_links)

    assert len(paper_links) == 2
    assert recommendations
    assert "loss_signal_quality" in axis_scores
    assert "loss_parallelism" in axis_scores


def test_infer_axis_scores_respects_keyword_boundaries() -> None:
    false_positive_scores = asana_ingest.infer_axis_scores(
        "Observed stddev drift in simulation metrics.",
        recommendations=[],
        paper_links=[],
    )
    assert "loss_signal_quality" not in false_positive_scores

    true_positive_scores = asana_ingest.infer_axis_scores(
        "We improved TD targets for value estimation.",
        recommendations=[],
        paper_links=[],
    )
    assert "loss_signal_quality" in true_positive_scores


def test_sync_project_research_writes_raw_and_normalized_cache(tmp_path, monkeypatch) -> None:
    def fake_fetch_project_tasks(project_gid: str, token: str, include_completed: bool = True):
        assert project_gid == "project-123"
        assert token == "token-abc"
        assert include_completed
        return [
            RawAsanaTask(
                gid="123",
                name="Critic calibration for distributional value targets",
                notes="We should improve critic calibration and evaluate TD targets.",
                permalink_url="https://app.asana.com/0/1/123",
                created_at="2026-03-01T00:00:00Z",
                modified_at="2026-03-02T00:00:00Z",
                custom_fields=[RawAsanaCustomField(name="Paper URL", display_value="https://arxiv.org/abs/1234.5678")],
            )
        ]

    def fake_fetch_task_stories(task_gid: str, token: str):
        assert task_gid == "123"
        assert token == "token-abc"
        return [
            RawAsanaStory(
                gid="story-1",
                type="comment",
                resource_subtype="comment_added",
                text="Recommendation: consider a distributional critic and more frequent learner updates.",
                created_at="2026-03-02T01:00:00Z",
            )
        ]

    monkeypatch.setattr(asana_ingest, "fetch_project_tasks", fake_fetch_project_tasks)
    monkeypatch.setattr(asana_ingest, "fetch_task_stories", fake_fetch_task_stories)

    raw_cache_path = tmp_path / "cache" / "asana_research_raw_cache_project-123_all.json"
    output_path = tmp_path / "cache" / "asana_research_cache.ndjson"

    records, summary = sync_project_research(
        project_gid="project-123",
        token="token-abc",
        raw_cache_path=raw_cache_path,
        output_path=output_path,
        include_completed=True,
        merge_output=False,
    )

    assert len(records) == 1
    assert summary.source_key == "project-123:all"
    assert summary.tasks_total == 1
    assert summary.story_refetch_count == 1
    assert summary.story_reuse_count == 0
    assert summary.records_written == 1
    assert summary.output_records_total == 1
    assert summary.paper_link_count >= 1
    assert summary.recommendation_count >= 1

    raw_cache_payload = json.loads(raw_cache_path.read_text(encoding="utf-8"))
    normalized_payload = _read_ndjson(output_path)

    assert raw_cache_payload["source_key"] == "project-123:all"
    assert "tasks" in raw_cache_payload
    assert normalized_payload[0]["paper_links"]
    assert normalized_payload[0]["recommendations"]
    assert normalized_payload[0]["inferred_axis_scores"]


def test_sync_project_research_reuses_story_cache_when_task_unchanged(tmp_path, monkeypatch) -> None:
    task = RawAsanaTask(
        gid="123",
        name="Experience rollout throughput study",
        notes="We should increase GPU actor parallelism.",
        permalink_url="https://app.asana.com/0/1/123",
        created_at="2026-03-01T00:00:00Z",
        modified_at="2026-03-02T00:00:00Z",
        custom_fields=[],
    )
    story = RawAsanaStory(
        gid="story-1",
        type="comment",
        resource_subtype="comment_added",
        text="Recommendation: focus on actor throughput across GPU shards.",
        created_at="2026-03-02T01:00:00Z",
    )

    def fake_fetch_project_tasks(project_gid: str, token: str, include_completed: bool = True):
        return [task]

    call_counter = {"count": 0}

    def fake_fetch_task_stories(task_gid: str, token: str):
        call_counter["count"] += 1
        return [story]

    monkeypatch.setattr(asana_ingest, "fetch_project_tasks", fake_fetch_project_tasks)
    monkeypatch.setattr(asana_ingest, "fetch_task_stories", fake_fetch_task_stories)

    raw_cache_path = tmp_path / "cache" / "asana_research_raw_cache_project-123_all.json"
    output_path = tmp_path / "cache" / "asana_research_cache.ndjson"

    _, first_summary = sync_project_research(
        project_gid="project-123",
        token="token-abc",
        raw_cache_path=raw_cache_path,
        output_path=output_path,
        merge_output=False,
    )
    _, second_summary = sync_project_research(
        project_gid="project-123",
        token="token-abc",
        raw_cache_path=raw_cache_path,
        output_path=output_path,
        merge_output=False,
    )

    assert call_counter["count"] == 1
    assert first_summary.story_refetch_count == 1
    assert second_summary.story_refetch_count == 0
    assert second_summary.story_reuse_count == 1


def test_sync_project_research_uses_section_fetch_and_merges_output(tmp_path, monkeypatch) -> None:
    def fake_fetch_project_tasks(project_gid: str, token: str, include_completed: bool = True):
        assert project_gid == "project-a"
        return [
            RawAsanaTask(
                gid="task-a",
                name="Curriculum model planning",
                notes="We should improve curriculum sampling.",
                permalink_url="https://app.asana.com/0/1/task-a",
                modified_at="2026-03-03T00:00:00Z",
            )
        ]

    def fake_fetch_section_tasks(project_gid: str, section_gid: str, token: str, include_completed: bool = True):
        assert project_gid == "project-b"
        assert section_gid == "section-b"
        return [
            RawAsanaTask(
                gid="task-b",
                name="Larger parameter sharding exploration",
                notes="Recommendation: consider FSDP sharding for larger policy models.",
                permalink_url="https://app.asana.com/0/1/task-b",
                modified_at="2026-03-04T00:00:00Z",
            )
        ]

    def fake_fetch_task_stories(task_gid: str, token: str):
        return []

    monkeypatch.setattr(asana_ingest, "fetch_project_tasks", fake_fetch_project_tasks)
    monkeypatch.setattr(asana_ingest, "fetch_section_tasks", fake_fetch_section_tasks)
    monkeypatch.setattr(asana_ingest, "fetch_task_stories", fake_fetch_task_stories)

    output_path = tmp_path / "cache" / "asana_research_cache.ndjson"

    _, summary_a = sync_project_research(
        project_gid="project-a",
        token="token",
        raw_cache_path=tmp_path / "cache" / "a_raw.json",
        output_path=output_path,
        merge_output=True,
    )
    _, summary_b = sync_project_research(
        project_gid="project-b",
        section_gid="section-b",
        token="token",
        raw_cache_path=tmp_path / "cache" / "b_raw.json",
        output_path=output_path,
        merge_output=True,
    )

    assert summary_a.output_records_total == 1
    assert summary_b.source_key == "project-b:section-b"
    assert not summary_b.used_project_fallback
    assert summary_b.output_records_total == 2

    payload = _read_ndjson(output_path)
    assert {record["gid"] for record in payload} == {"task-a", "task-b"}


def test_sync_project_research_falls_back_when_section_empty(tmp_path, monkeypatch) -> None:
    def fake_fetch_project_tasks(project_gid: str, token: str, include_completed: bool = True):
        return [
            RawAsanaTask(
                gid="task-project",
                name="Project fallback task",
                notes="We should improve rollout throughput.",
                permalink_url="https://app.asana.com/0/1/task-project",
                modified_at="2026-03-05T00:00:00Z",
            )
        ]

    def fake_fetch_section_tasks(project_gid: str, section_gid: str, token: str, include_completed: bool = True):
        return []

    monkeypatch.setattr(asana_ingest, "fetch_project_tasks", fake_fetch_project_tasks)
    monkeypatch.setattr(asana_ingest, "fetch_section_tasks", fake_fetch_section_tasks)
    monkeypatch.setattr(asana_ingest, "fetch_task_stories", lambda task_gid, token: [])

    records, summary = sync_project_research(
        project_gid="project-1",
        section_gid="section-1",
        token="token",
        raw_cache_path=tmp_path / "cache" / "raw.json",
        output_path=tmp_path / "cache" / "out.json",
        merge_output=False,
    )

    assert summary.used_project_fallback
    assert summary.tasks_total == 1
    assert len(records) == 1
