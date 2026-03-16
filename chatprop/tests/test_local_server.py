from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import metta.chatprop.local.backend.server as server_module
from metta.chatprop.config import ChatpropConfig, DaemonConfig, SourceConfig
from metta.chatprop.local.backend.server import (
    _branch_outcome_from_sources,
    _build_catalog,
    _cached_outcome_is_fresh,
    _extract_branches,
    _extract_session_cwd,
    _flowchart_options_from_payload,
    _normalize_closed_pr_record,
    _normalize_merged_pr_record,
    _normalize_uploaded_snapshot_payload,
    _parse_archived_session_id,
    _parse_output_path,
    _read_uploaded_snapshot_records,
    _repo_from_cwd,
    _repo_root_for_explicit_skills,
    _resolve_frontend_target,
    _select_pr_record,
    _store_uploaded_snapshot,
    parse_args,
)
from metta.chatprop.scanner import TranscriptFile


def _make_config(tmp_path: Path) -> ChatpropConfig:
    return ChatpropConfig(
        claude_code=SourceConfig(path=tmp_path / "claude"),
        codex=SourceConfig(path=tmp_path / "codex"),
        daemon=DaemonConfig(
            poll_interval_seconds=1,
            inactivity_threshold_seconds=0,
        ),
        state_dir=tmp_path / "state",
    )


def test_resolve_frontend_target_blocks_path_traversal(tmp_path: Path) -> None:
    base = tmp_path / "frontend" / "static"
    base.mkdir(parents=True)

    assert _resolve_frontend_target(base, "../secrets.txt") is None
    assert _resolve_frontend_target(base, "../../etc/passwd") is None
    assert _resolve_frontend_target(base, "assets/app.js") == (base / "assets" / "app.js").resolve()


def test_extract_branches_dedupes_and_trims() -> None:
    payload = {
        "branches": [
            " feature/a ",
            "feature/b",
            "feature/a",
            "",
            "   ",
            42,
        ]
    }
    assert _extract_branches(payload) == ["feature/a", "feature/b"]


def test_extract_branches_rejects_non_list() -> None:
    assert _extract_branches({"branches": "feature/a"}) == []


def test_parse_args_defaults() -> None:
    args = parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_parse_args_normalizes_base_path() -> None:
    args = parse_args(["--base-path", "/chatprop/"])
    assert args.base_path == "/chatprop"


def test_parse_args_rejects_relative_base_path() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--base-path", "chatprop"])


def test_parse_archived_session_id_strips_mtime_suffix() -> None:
    path = Path("/tmp/transcripts/codex/abc-12345.jsonl")
    assert _parse_archived_session_id(path) == "abc"


def test_select_pr_record_prefers_exact_branch_and_merged() -> None:
    records = [
        {"headRefName": "feature-x", "updatedAt": "2026-02-26T10:00:00+00:00", "mergedAt": None},
        {
            "headRefName": "feature-x",
            "updatedAt": "2026-02-27T10:00:00+00:00",
            "mergedAt": "2026-02-27T11:00:00+00:00",
        },
        {
            "headRefName": "other-branch",
            "updatedAt": "2026-02-27T12:00:00+00:00",
            "mergedAt": "2026-02-27T12:30:00+00:00",
        },
    ]
    selected = _select_pr_record("feature-x", records)
    assert selected is not None
    assert selected["headRefName"] == "feature-x"
    assert selected["mergedAt"] == "2026-02-27T11:00:00+00:00"


def test_cached_outcome_is_fresh_only_with_recent_timestamp() -> None:
    fresh = {"fetched_at": datetime.now(tz=UTC).isoformat()}
    stale = {"fetched_at": (datetime.now(tz=UTC) - timedelta(days=2)).isoformat()}
    invalid = {"fetched_at": "not-a-date"}

    assert _cached_outcome_is_fresh(fresh)
    assert not _cached_outcome_is_fresh(stale)
    assert not _cached_outcome_is_fresh(invalid)


def test_extract_session_cwd_reads_first_present_cwd(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-02-27T12:00:00Z","type":"user"}',
                '{"timestamp":"2026-02-27T12:00:01Z","cwd":"/tmp/repo-a","type":"assistant"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert _extract_session_cwd(transcript) == "/tmp/repo-a"


def test_repo_from_cwd_prefers_git_root_and_caches(tmp_path: Path) -> None:
    repo_root = tmp_path / "tribal-village"
    nested = repo_root / "src" / "app"
    (repo_root / ".git").mkdir(parents=True)
    nested.mkdir(parents=True)

    cache: dict[str, str | None] = {}
    assert _repo_from_cwd(str(nested), cache=cache) == "tribal-village"
    assert cache[str(nested)] == "tribal-village"


def test_branch_outcome_uses_merged_pr_lookup_without_shell_calls() -> None:
    lookup = {
        "by_branch": {
            "feature-x": {
                "number": 123,
                "title": "Feature X",
                "url": "https://example.com/pr/123",
                "mergedAt": "2026-02-27T10:00:00+00:00",
                "closedAt": "2026-02-27T10:00:00+00:00",
                "headRefName": "feature-x",
                "baseRefName": "main",
            }
        },
        "by_repo_branch": {},
    }
    outcome = _branch_outcome_from_sources(
        "feature-x",
        repo="metta",
        repos=["metta"],
        include_pr_lookup=True,
        include_commit_lookup=False,
        merged_pr_lookup=lookup,
    )

    assert outcome["pr_state"] == "merged"
    assert outcome["pr_number"] == 123
    assert outcome["pr_title"] == "Feature X"
    assert outcome["pr_base_ref"] == "main"


def test_branch_outcome_prefers_repo_specific_merged_match() -> None:
    lookup = {
        "by_branch": {
            "feature-x": {
                "number": 11,
                "title": "Wrong Repo Match",
                "url": "https://example.com/pr/11",
                "mergedAt": "2026-02-27T09:00:00+00:00",
                "closedAt": "2026-02-27T09:00:00+00:00",
                "headRefName": "feature-x",
                "baseRefName": "main",
            }
        },
        "by_repo_branch": {
            "tribal-village\0feature-x": {
                "number": 42,
                "title": "Right Repo Match",
                "url": "https://example.com/pr/42",
                "mergedAt": "2026-02-27T10:00:00+00:00",
                "closedAt": "2026-02-27T10:00:00+00:00",
                "headRefName": "feature-x",
                "baseRefName": "main",
            }
        },
    }
    outcome = _branch_outcome_from_sources(
        "feature-x",
        repo="tribal-village",
        repos=["tribal-village"],
        include_pr_lookup=False,
        include_commit_lookup=False,
        merged_pr_lookup=lookup,
    )
    assert outcome["pr_state"] == "merged"
    assert outcome["pr_number"] == 42


def test_normalize_closed_pr_record_marks_landed_via_closed_main_match() -> None:
    normalized = _normalize_closed_pr_record(
        {
            "number": 1234,
            "title": "Some stacked PR",
            "url": "https://github.com/Metta-AI/metta/pull/1234",
            "closedAt": "2026-02-27T18:24:22Z",
            "headRefName": "relh/stacked-branch",
            "baseRefName": "main",
            "updatedAt": "2026-02-27T18:24:24Z",
            "repository": {
                "name": "metta",
                "nameWithOwner": "Metta-AI/metta",
            },
        }
    )
    assert normalized is not None
    assert normalized["number"] == 1234
    assert normalized["mergedAt"] == "2026-02-27T18:24:22Z"
    assert normalized["closedAt"] == "2026-02-27T18:24:22Z"
    assert normalized["landedVia"] == "closed_pr_number_on_main"


def test_normalize_merged_pr_record_trims_repo_metadata() -> None:
    normalized = _normalize_merged_pr_record(
        {
            "number": 5678,
            "title": "  Cleanup flowchart payloads  ",
            "url": "  https://github.com/Metta-AI/metta/pull/5678  ",
            "mergedAt": " 2026-02-28T01:02:03Z ",
            "closedAt": " 2026-02-28T01:03:00Z ",
            "headRefName": " relh/cleanup-chatprop-flowchart ",
            "baseRefName": " main ",
            "updatedAt": " 2026-02-28T01:04:00Z ",
            "repository": {
                "name": " metta ",
                "nameWithOwner": " Metta-AI/metta ",
            },
        }
    )
    assert normalized is not None
    assert normalized["title"] == "Cleanup flowchart payloads"
    assert normalized["url"] == "https://github.com/Metta-AI/metta/pull/5678"
    assert normalized["mergedAt"] == "2026-02-28T01:02:03Z"
    assert normalized["closedAt"] == "2026-02-28T01:03:00Z"
    assert normalized["headRefName"] == "relh/cleanup-chatprop-flowchart"
    assert normalized["baseRefName"] == "main"
    assert normalized["updatedAt"] == "2026-02-28T01:04:00Z"
    assert normalized["repositoryName"] == "metta"
    assert normalized["repositoryNameWithOwner"] == "Metta-AI/metta"


def test_flowchart_options_from_payload_defaults() -> None:
    options = _flowchart_options_from_payload({})
    assert options is not None
    assert options["min_node_count"] == 1
    assert options["min_edge_count"] == 1
    assert options["max_nodes"] == 120
    assert options["max_edges"] == 350


def test_flowchart_options_from_payload_accepts_string_numbers() -> None:
    options = _flowchart_options_from_payload(
        {
            "min_node_count": "2",
            "min_edge_count": "3",
            "max_nodes": "150",
            "max_edges": "400",
        }
    )
    assert options is not None
    assert options == {
        "min_node_count": 2,
        "min_edge_count": 3,
        "max_nodes": 150,
        "max_edges": 400,
    }


def test_flowchart_options_from_payload_rejects_invalid_values() -> None:
    assert _flowchart_options_from_payload({"max_nodes": 0}) is None
    assert _flowchart_options_from_payload({"max_edges": "abc"}) is None
    assert _flowchart_options_from_payload({"min_node_count": True}) is None


def test_parse_output_path_handles_blank_and_expands() -> None:
    assert _parse_output_path("") is None
    assert _parse_output_path("   ") is None
    parsed = _parse_output_path("~/tmp/chatprop-flowchart.mmd")
    assert parsed is not None
    assert parsed.is_absolute()


def test_normalize_uploaded_snapshot_payload_accepts_flowchart_shape() -> None:
    normalized = _normalize_uploaded_snapshot_payload(
        {
            "name": "laptop-snapshot",
            "snapshot": {
                "session_count": 4,
                "branch_count": 3,
                "workflow_graph": {
                    "graph_scope": "uploaded_snapshot",
                    "revision_prevention_scope": "uploaded_snapshot",
                    "nodes": [
                        {"id": "implicit_fn:fix", "label": "fix(x)", "kind": "implicit", "count": 2},
                        {"id": "explicit:pr.fix-ci", "label": "pr.fix-ci", "kind": "explicit", "count": 1},
                    ],
                    "edges": [
                        {
                            "source": "implicit_fn:fix",
                            "target": "explicit:pr.fix-ci",
                            "phase": "explicit_ref",
                            "count": 1,
                        }
                    ],
                },
            },
        }
    )
    assert normalized is not None
    assert normalized["name"] == "laptop-snapshot"
    assert normalized["source_key"] == "laptop-snapshot"
    assert normalized["session_count"] == 4
    assert normalized["branch_count"] == 3
    assert normalized["workflow_graph"]["node_count"] == 2
    assert normalized["workflow_graph"]["edge_count"] == 1


def test_normalize_uploaded_snapshot_payload_rejects_missing_graph() -> None:
    assert _normalize_uploaded_snapshot_payload({"snapshot": {"session_count": 1}}) is None


def test_store_uploaded_snapshot_replaces_existing_source_key(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    first = _store_uploaded_snapshot(
        config,
        {
            "source_key": "machine-a",
            "name": "Machine A",
            "snapshot": {
                "session_count": 3,
                "branch_count": 2,
                "workflow_graph": {
                    "nodes": [{"id": "implicit_fn:fix", "label": "fix(x)", "kind": "implicit", "count": 2}],
                    "edges": [],
                },
            },
        },
    )
    second = _store_uploaded_snapshot(
        config,
        {
            "source_key": "machine-a",
            "name": "Machine A",
            "snapshot": {
                "session_count": 9,
                "branch_count": 4,
                "workflow_graph": {
                    "nodes": [{"id": "implicit_fn:fix", "label": "fix(x)", "kind": "implicit", "count": 5}],
                    "edges": [],
                },
            },
        },
    )

    records = _read_uploaded_snapshot_records(config)
    assert len(records) == 1
    assert first["snapshot_id"] == second["snapshot_id"]
    assert second["session_count"] == 9
    assert second["branch_count"] == 4
    assert records[0]["source_key"] == "machine-a"
    assert records[0]["workflow_graph"]["nodes"][0]["count"] == 5


def test_build_catalog_keeps_single_indexed_branch_feature_chunk(tmp_path: Path, monkeypatch) -> None:
    config = _make_config(tmp_path)
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text("", encoding="utf-8")
    transcript = TranscriptFile(
        path=transcript_path,
        session_id="session-1",
        source="codex",
        size_bytes=0,
    )
    analyzed_segment_counts: list[int] = []

    def _unexpected_segment_inference(_path: Path) -> list[object]:
        raise AssertionError("segment inference should be skipped for single indexed branch sessions")

    def _fake_analyze(
        *,
        transcript_path: Path,
        branch_segments: list[object],
        explicit_skills: list[str],
    ) -> list[dict[str, object]]:
        del transcript_path, explicit_skills
        analyzed_segment_counts.append(len(branch_segments))
        return server_module.build_feature_chunks_from_segments(branch_segments)

    monkeypatch.setattr(
        server_module,
        "_read_archive_index",
        lambda _config: {transcript_path.resolve(): {"feature/solo"}},
    )
    monkeypatch.setattr(server_module, "_read_archive_metadata_windows", lambda _config: {})
    monkeypatch.setattr(server_module, "scan_archived", lambda _config: [transcript])
    monkeypatch.setattr(server_module, "extract_branch_segments_from_transcript", _unexpected_segment_inference)
    monkeypatch.setattr(
        server_module,
        "_extract_session_window",
        lambda _path: ("2026-02-27T10:00:00Z", "2026-02-27T10:10:00Z"),
    )
    monkeypatch.setattr(server_module, "_extract_session_cwd", lambda _path: None)
    monkeypatch.setattr(server_module, "_load_branch_cache", lambda _config: {})
    monkeypatch.setattr(server_module, "_load_merged_pr_index", lambda _config: {"by_branch": {}, "by_repo_branch": {}})
    monkeypatch.setattr(server_module, "_get_branch_outcome", lambda *args, **kwargs: {})
    monkeypatch.setattr(server_module, "_write_branch_cache", lambda _config, _cache: None)
    monkeypatch.setattr(server_module, "analyze_session_feature_chunks", _fake_analyze)
    monkeypatch.setattr(server_module, "load_explicit_skills", lambda _repo_root: [])

    payload = _build_catalog(config, refresh=False)

    assert analyzed_segment_counts == [1]
    assert payload["session_count"] == 1
    session = payload["sessions"][0]
    assert session["feature_count"] == 1
    assert [chunk["branch"] for chunk in session["feature_chunks"]] == ["feature/solo"]

    branch_row = payload["branches"][0]
    assert branch_row["name"] == "feature/solo"
    assert branch_row["feature_count"] == 1


def test_build_catalog_loads_explicit_skills_from_repo_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    config = _make_config(tmp_path)
    fake_cwd = tmp_path / "chatprop"
    fake_cwd.mkdir(parents=True)
    loaded_roots: list[Path] = []

    monkeypatch.setattr(server_module.Path, "cwd", classmethod(lambda cls: fake_cwd))
    monkeypatch.setattr(server_module, "_read_archive_index", lambda _config: {})
    monkeypatch.setattr(server_module, "_read_archive_metadata_windows", lambda _config: {})
    monkeypatch.setattr(server_module, "scan_archived", lambda _config: [])
    monkeypatch.setattr(server_module, "_load_branch_cache", lambda _config: {})
    monkeypatch.setattr(server_module, "_load_merged_pr_index", lambda _config: {"by_branch": {}, "by_repo_branch": {}})
    monkeypatch.setattr(server_module, "_write_branch_cache", lambda _config, _cache: None)
    monkeypatch.setattr(
        server_module,
        "load_explicit_skills",
        lambda repo_root: loaded_roots.append(repo_root) or [],
    )

    _build_catalog(config, refresh=False)

    assert loaded_roots == [_repo_root_for_explicit_skills()]
    assert loaded_roots[0] != fake_cwd
    assert (loaded_roots[0] / "skills").is_dir()


def test_build_catalog_merges_uploaded_snapshots_when_local_archive_is_empty(tmp_path: Path, monkeypatch) -> None:
    config = _make_config(tmp_path)

    monkeypatch.setattr(server_module, "_read_archive_index", lambda _config: {})
    monkeypatch.setattr(server_module, "_read_archive_metadata_windows", lambda _config: {})
    monkeypatch.setattr(server_module, "scan_archived", lambda _config: [])
    monkeypatch.setattr(server_module, "_load_branch_cache", lambda _config: {})
    monkeypatch.setattr(server_module, "_load_merged_pr_index", lambda _config: {"by_branch": {}, "by_repo_branch": {}})
    monkeypatch.setattr(server_module, "_write_branch_cache", lambda _config, _cache: None)
    monkeypatch.setattr(server_module, "load_explicit_skills", lambda _repo_root: ["pr.fix-ci", "pr.summary"])
    monkeypatch.setattr(
        server_module,
        "_read_uploaded_snapshot_records",
        lambda _config: [
            {
                "snapshot_id": "up-1",
                "uploaded_at": "2026-03-05T16:00:00+00:00",
                "name": "remote-sample",
                "session_count": 12,
                "branch_count": 5,
                "workflow_graph": {
                    "graph_scope": "uploaded_snapshot",
                    "revision_prevention_scope": "uploaded_snapshot",
                    "node_count": 2,
                    "edge_count": 1,
                    "nodes": [
                        {"id": "implicit_fn:fix", "label": "fix(x)", "kind": "implicit", "count": 7},
                        {"id": "explicit:pr.fix-ci", "label": "pr.fix-ci", "kind": "explicit", "count": 3},
                    ],
                    "edges": [
                        {
                            "source": "implicit_fn:fix",
                            "target": "explicit:pr.fix-ci",
                            "phase": "explicit_ref",
                            "count": 3,
                        }
                    ],
                    "revision_prevention": [],
                },
            }
        ],
    )

    payload = _build_catalog(config, refresh=False)

    assert payload["session_count"] == 12
    assert payload["branch_count"] == 5
    assert payload["uploaded_snapshot_count"] == 1
    assert payload["uploaded_session_count"] == 12
    assert payload["uploaded_branch_count"] == 5
    assert payload["workflow_graph"]["graph_scope"] == "all_feature_chunks_plus_uploaded_snapshots"
    assert payload["skill_dendrogram"]["skill_count"] == 2
    assert payload["uploaded_snapshots"][0]["node_count"] == 2
