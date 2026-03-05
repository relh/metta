from pathlib import Path

from metta.chatprop.config import ChatpropConfig, DaemonConfig, SourceConfig
from metta.chatprop.local.daemon import get_status


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


def test_status_handles_empty_archive(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    status = get_status(config)
    assert status.transcript_count == 0
    assert status.metadata_count == 0
    assert status.indexed_branch_count == 0
    assert status.manifest_entry_count == 0
