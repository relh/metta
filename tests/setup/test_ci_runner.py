"""Tests for the metta ci command.

Uses typer's CliRunner for in-process invocation instead of subprocess to avoid
multi-second Python startup overhead.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from metta.setup.metta_cli import app
from metta.setup.tools.ci_runner import STAGE_MAP

pytestmark = pytest.mark.setup

runner = CliRunner(mix_stderr=False)


def test_ci_help_shows_all_stages() -> None:
    """Test that metta ci --help shows all available stages."""
    result = runner.invoke(app, ["ci", "--help"])

    assert result.exit_code == 0
    # Check that key stages are mentioned in help
    assert "lint" in result.stdout
    assert "python-tests" in result.stdout
    assert "cpp-tests" in result.stdout
    assert "cpp-benchmarks" in result.stdout


def test_ci_invalid_stage_fails() -> None:
    """Test that running metta ci with an invalid stage fails with helpful error."""
    result = runner.invoke(app, ["ci", "invalid-stage"])

    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Unknown stage" in combined


def test_ci_unknown_option_treated_as_stage() -> None:
    """Unknown options without a valid stage are caught by stage validation."""
    result = runner.invoke(app, ["ci", "--skip-package", "tests"])

    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Unknown stage" in combined


def test_stage_map_contains_expected_stages() -> None:
    """Verify the stage map has all expected stages."""
    expected = {"lint", "python-tests", "cpp-tests", "cpp-benchmarks", "nim-tests", "recipe-tests"}
    assert expected.issubset(set(STAGE_MAP.keys()))
