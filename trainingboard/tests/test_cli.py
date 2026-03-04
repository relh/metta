from click.testing import CliRunner

from metta.trainingboard.cli import main


def test_cli_help_lists_expected_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "ingest-asana" in result.output
    assert "snapshot" in result.output
