from pathlib import Path

from metta.chatprop.config import default_state_dir, load_config


def test_load_config_uses_defaults_for_malformed_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("sources = [", encoding="utf-8")

    config = load_config(config_path)

    assert config.claude_code.path == Path("~/.claude/projects").expanduser()
    assert config.codex.path == Path("~/.codex/sessions").expanduser()
    assert config.daemon.poll_interval_seconds == 30
    assert config.daemon.inactivity_threshold_seconds == 60
    assert config.state_dir == default_state_dir()
