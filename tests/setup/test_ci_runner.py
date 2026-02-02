"""Tests for the metta ci command.

Uses typer's CliRunner for in-process invocation instead of subprocess to avoid
multi-second Python startup overhead.
"""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from metta.setup.metta_cli import app
from metta.setup.tools.ci_runner import ALLOWED_SKIP_PACKAGES, _normalize_python_stage_args

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
    assert "python-tests-and-benchmarks" not in result.stdout


def test_ci_invalid_stage_fails() -> None:
    """Test that running metta ci with an invalid stage fails with helpful error."""
    result = runner.invoke(app, ["ci", "--stage", "invalid-stage"])

    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Unknown stage" in combined


def test_ci_requires_stage_for_extra_args() -> None:
    """Extra args without --stage should fail fast."""
    result = runner.invoke(app, ["ci", "--", "--skip-package", "tests"])

    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "Extra arguments require specifying a --stage" in combined


def test_ci_non_python_stage_rejects_extra_args() -> None:
    """Stages that do not accept extra args should error."""
    result = runner.invoke(app, ["ci", "--stage", "lint", "--", "--skip-package", "tests"])

    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert "does not accept extra arguments" in combined


def test_normalize_python_stage_args_allows_known_package() -> None:
    package = next(iter(ALLOWED_SKIP_PACKAGES))
    result = _normalize_python_stage_args(["--skip-package", package])
    assert result == ["--skip-package", package]


def test_normalize_python_stage_args_rejects_unknown_package() -> None:
    with pytest.raises(typer.Exit):
        _normalize_python_stage_args(["--skip-package", "does-not-exist"])
