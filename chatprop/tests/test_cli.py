from click.testing import CliRunner

from metta.chatprop.cli import main


def test_cli_help_contains_analysis_and_local_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "find" in result.output
    assert "analyze" in result.output
    assert "propose" in result.output
    assert "daemon" in result.output
    assert "serve" in result.output
    assert "status" in result.output
    assert "flowchart" in result.output
    assert "init" in result.output


def test_cli_init_writes_config_file(tmp_path) -> None:
    config_path = tmp_path / "chatprop.toml"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "init",
            "--config",
            str(config_path),
            "--claude-code-path",
            "/tmp/claude-sessions",
            "--codex-path",
            "/tmp/codex-sessions",
            "--state-dir",
            "/tmp/chatprop-state",
        ],
    )
    assert result.exit_code == 0
    assert config_path.is_file()
    text = config_path.read_text(encoding="utf-8")
    assert "/tmp/claude-sessions" in text
    assert "/tmp/codex-sessions" in text
    assert "/tmp/chatprop-state" in text
