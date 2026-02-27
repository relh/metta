from pathlib import Path

from metta.chatprop.local.indexer import (
    extract_branch_segments_from_transcript,
    extract_branches_from_transcript,
    extract_work_branches_from_transcript,
)


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_extract_work_branches_treats_main_as_prelude(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(
        transcript,
        [
            '{"timestamp":"2026-02-27T10:00:00Z","gitBranch":"main"}',
            '{"timestamp":"2026-02-27T10:05:00Z","payload":{"git":{"branch":"feature/a"}}}',
        ],
    )

    segments = extract_branch_segments_from_transcript(transcript)
    assert [segment.branch for segment in segments] == ["main", "feature/a"]
    assert extract_work_branches_from_transcript(transcript) == ["feature/a"]
    assert extract_branches_from_transcript(transcript) == {"feature/a"}


def test_extract_work_branches_keeps_non_main_transitions(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(
        transcript,
        [
            '{"timestamp":"2026-02-27T10:00:00Z","gitBranch":"feature/a"}',
            '{"timestamp":"2026-02-27T10:01:00Z","gitBranch":"feature/a"}',
            '{"timestamp":"2026-02-27T10:02:00Z","gitBranch":"feature/b"}',
            '{"timestamp":"2026-02-27T10:03:00Z","gitBranch":"main"}',
        ],
    )

    segments = extract_branch_segments_from_transcript(transcript)
    assert [segment.branch for segment in segments] == ["feature/a", "feature/b", "main"]
    assert extract_work_branches_from_transcript(transcript) == ["feature/a", "feature/b"]


def test_extract_work_branches_normalizes_main_like_branches(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(
        transcript,
        [
            '{"timestamp":"2026-02-27T10:00:00Z","gitBranch":"HEAD"}',
            '{"timestamp":"2026-02-27T10:01:00Z","gitBranch":"master"}',
            '{"timestamp":"2026-02-27T10:02:00Z","gitBranch":"main"}',
            '{"timestamp":"2026-02-27T10:03:00Z","gitBranch":""}',
        ],
    )

    segments = extract_branch_segments_from_transcript(transcript)
    assert [segment.branch for segment in segments] == ["main"]
    assert extract_work_branches_from_transcript(transcript) == ["main"]
    assert extract_branches_from_transcript(transcript) == {"main"}
