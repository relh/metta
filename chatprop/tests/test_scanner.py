import json
from pathlib import Path

from metta.chatprop.config import ChatpropConfig, DaemonConfig, SourceConfig
from metta.chatprop.scanner import find_transcripts_for_branches, read_transcript


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


def test_find_transcripts_uses_archive_index(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    archive_file = config.state_dir / "archive" / "transcripts" / "codex" / "session-x-123.jsonl"
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    archive_file.write_text(
        json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}) + "\n",
        encoding="utf-8",
    )

    index_path = config.state_dir / "archive" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-01-01T00:00:00+00:00",
                "branches": {"feature/x": ["transcripts/codex/session-x-123.jsonl"]},
            }
        ),
        encoding="utf-8",
    )

    matches = find_transcripts_for_branches(config, ["feature/x"])
    assert len(matches) == 1
    assert matches[0].session_id == "session-x"
    assert matches[0].matched_branches == ["feature/x"]


def test_read_transcript_skips_unhashable_message_type(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"type": [], "message": {"content": "broken"}}),
                json.dumps({"type": "user", "message": {"content": "hello"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert read_transcript(transcript) == "[USER]: hello"


def test_read_transcript_skips_unhashable_event_type(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"type": "event_msg", "payload": {"type": [], "message": "broken"}}),
                json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert read_transcript(transcript) == "[USER]: hello"
