import json
from pathlib import Path

from metta.chatprop.local.indexer import BranchSegment
from metta.chatprop.local.workflow import (
    SkillGraphAccumulator,
    analyze_session_feature_chunks,
    build_feature_chunks_from_segments,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    payload = "\n".join(json.dumps(row) for row in rows) + "\n"
    path.write_text(payload, encoding="utf-8")


def test_build_feature_chunks_folds_main_prelude_into_first_feature() -> None:
    segments = [
        BranchSegment(branch="main", started_at="2026-02-27T10:00:00Z", ended_at="2026-02-27T10:01:00Z"),
        BranchSegment(branch="feature/a", started_at="2026-02-27T10:01:00Z", ended_at="2026-02-27T10:05:00Z"),
    ]
    chunks = build_feature_chunks_from_segments(segments)
    assert chunks == [
        {
            "branch": "feature/a",
            "started_at": "2026-02-27T10:00:00Z",
            "ended_at": "2026-02-27T10:05:00Z",
        }
    ]


def test_build_feature_chunks_splits_non_main_transitions() -> None:
    segments = [
        BranchSegment(branch="feature/a", started_at="2026-02-27T10:00:00Z", ended_at="2026-02-27T10:02:00Z"),
        BranchSegment(branch="feature/b", started_at="2026-02-27T10:02:00Z", ended_at="2026-02-27T10:04:00Z"),
    ]
    chunks = build_feature_chunks_from_segments(segments)
    assert [chunk["branch"] for chunk in chunks] == ["feature/a", "feature/b"]


def test_analyze_session_feature_chunks_splits_planning_vs_revision(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-02-27T10:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Implement feature A and add tests"},
            },
            {
                "timestamp": "2026-02-27T10:01:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Done. Feature A is complete and ready for review."},
            },
            {
                "timestamp": "2026-02-27T10:02:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Please fix CI and use pr.fix-ci if helpful"},
            },
            {
                "timestamp": "2026-02-27T10:03:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Fixed CI and pushed updates."},
            },
        ],
    )

    segments = [
        BranchSegment(branch="main", started_at="2026-02-27T10:00:00Z", ended_at="2026-02-27T10:00:30Z"),
        BranchSegment(branch="feature/a", started_at="2026-02-27T10:00:30Z", ended_at="2026-02-27T10:03:00Z"),
    ]

    chunks = analyze_session_feature_chunks(
        transcript_path=transcript,
        branch_segments=segments,
        explicit_skills=["pr.fix-ci"],
    )
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["branch"] == "feature/a"
    assert chunk["believed_done_at"] == "2026-02-27T10:01:00Z"
    assert chunk["has_revision"] is True
    assert chunk["phase_a"]["user_message_count"] == 1
    assert chunk["phase_b"]["user_message_count"] == 1
    assert "explicit:pr.fix-ci" in chunk["explicit_skill_refs"]


def test_skill_graph_accumulator_adds_revision_prevention_link() -> None:
    graph = SkillGraphAccumulator(explicit_skills=["pr.fix-ci"])
    graph.add_feature_chunk(
        session_id="s-1",
        repo="metta",
        chunk={
            "branch": "feature/a",
            "explicit_skill_refs": ["explicit:pr.fix-ci"],
            "implicit_skill_labels": {
                "implicit_fn:implement": "implement(x)",
                "implicit_fn:test": "test(x)",
                "implicit_fn:fix": "fix(x)",
            },
            "phase_a": {
                "skills": ["implicit_fn:implement", "implicit_fn:test"],
                "implicit_invocations": [
                    {"skill_id": "implicit_fn:implement", "argument": "feature chunk"},
                    {"skill_id": "implicit_fn:test", "argument": "ci"},
                ],
            },
            "phase_b": {
                "skills": ["implicit_fn:fix"],
                "implicit_invocations": [
                    {"skill_id": "implicit_fn:fix", "argument": "ci failures"},
                ],
            },
        },
    )
    payload = graph.to_dict()
    assert payload["node_count"] >= 4
    assert any(edge["phase"] == "handoff" for edge in payload["edges"])
    assert payload["revision_prevention"]
    assert payload["revision_prevention"][0]["planning_skill"] == "implicit_fn:test"
    assert payload["revision_prevention"][0]["revision_skill"] == "implicit_fn:fix"


def test_skill_graph_accumulator_can_skip_revision_prevention_for_unmerged_chunks() -> None:
    graph = SkillGraphAccumulator(explicit_skills=[])
    graph.add_feature_chunk(
        session_id="s-2",
        repo="metta",
        include_revision_prevention=False,
        chunk={
            "branch": "feature/unmerged",
            "phase_a": {
                "skills": ["implicit_fn:implement", "implicit_fn:test"],
                "implicit_invocations": [
                    {"skill_id": "implicit_fn:implement", "argument": "feature slice"},
                    {"skill_id": "implicit_fn:test", "argument": "lint"},
                ],
            },
            "phase_b": {
                "skills": ["implicit_fn:fix"],
                "implicit_invocations": [
                    {"skill_id": "implicit_fn:fix", "argument": "lint"},
                ],
            },
            "explicit_skill_refs": [],
            "implicit_skill_labels": {
                "implicit_fn:implement": "implement(x)",
                "implicit_fn:test": "test(x)",
                "implicit_fn:fix": "fix(x)",
            },
        },
    )
    payload = graph.to_dict()
    assert payload["node_count"] >= 3
    assert any(edge["phase"] == "handoff" for edge in payload["edges"])
    assert payload["revision_prevention"] == []


def test_analyze_session_feature_chunks_extracts_function_argument_invocations(tmp_path: Path) -> None:
    transcript = tmp_path / "session_args.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-02-27T11:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Please fix flaky ci for scanner.py"},
            },
            {
                "timestamp": "2026-02-27T11:01:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Done and ready for merge"},
            },
        ],
    )

    segments = [
        BranchSegment(branch="feature/x", started_at="2026-02-27T11:00:00Z", ended_at="2026-02-27T11:02:00Z"),
    ]
    chunks = analyze_session_feature_chunks(
        transcript_path=transcript,
        branch_segments=segments,
        explicit_skills=[],
    )
    assert len(chunks) == 1
    invocations = chunks[0]["phase_a"]["implicit_invocations"]
    assert invocations
    assert invocations[0]["skill_id"] == "implicit_fn:fix"
    assert "flaky ci" in invocations[0]["argument"]


def test_believed_done_tracks_last_feature_request_before_revision(tmp_path: Path) -> None:
    transcript = tmp_path / "session_last_feature.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-02-27T12:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Implement parser changes"},
            },
            {
                "timestamp": "2026-02-27T12:01:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Done with parser"},
            },
            {
                "timestamp": "2026-02-27T12:02:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Also add tests for parser edge cases"},
            },
            {
                "timestamp": "2026-02-27T12:03:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Done now, ready for review"},
            },
            {
                "timestamp": "2026-02-27T12:04:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Please fix lint failures"},
            },
        ],
    )
    segments = [
        BranchSegment(branch="feature/parser", started_at="2026-02-27T12:00:00Z", ended_at="2026-02-27T12:05:00Z"),
    ]
    chunks = analyze_session_feature_chunks(
        transcript_path=transcript,
        branch_segments=segments,
        explicit_skills=[],
    )
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["believed_done_at"] == "2026-02-27T12:03:00Z"
    assert chunk["believed_done_inferred"] is False
    assert chunk["feature_request_count"] == 2
    assert chunk["revision_request_count"] == 1


def test_believed_done_infers_boundary_when_revision_exists_without_done_cue(tmp_path: Path) -> None:
    transcript = tmp_path / "session_inferred_done.jsonl"
    _write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-02-27T13:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Implement feature flags"},
            },
            {
                "timestamp": "2026-02-27T13:01:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "I made updates to the branch"},
            },
            {
                "timestamp": "2026-02-27T13:02:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Address review comment about tests"},
            },
        ],
    )
    segments = [
        BranchSegment(branch="feature/flags", started_at="2026-02-27T13:00:00Z", ended_at="2026-02-27T13:03:00Z"),
    ]
    chunks = analyze_session_feature_chunks(
        transcript_path=transcript,
        branch_segments=segments,
        explicit_skills=[],
    )
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["believed_done_at"] == "2026-02-27T13:02:00Z"
    assert chunk["believed_done_inferred"] is True
    assert chunk["phase_b"]["user_message_count"] == 1
