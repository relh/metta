from datetime import UTC, datetime, timedelta
from pathlib import Path

from metta.chatprop.local.backend.server import (
    _branch_outcome_from_sources,
    _cached_outcome_is_fresh,
    _extract_branches,
    _extract_session_cwd,
    _normalize_closed_pr_record,
    _parse_archived_session_id,
    _repo_from_cwd,
    _resolve_frontend_target,
    _select_pr_record,
    parse_args,
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
