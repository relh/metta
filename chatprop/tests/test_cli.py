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
