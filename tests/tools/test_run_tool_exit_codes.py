"""Test that run_tool.py correctly propagates exit codes.

Tests call main() directly instead of spawning a subprocess to avoid the
multi-second overhead of ``uv run`` process startup.
"""

from unittest.mock import patch

from metta.common.tool.run_tool import main


def test_run_tool_returns_exit_code_1_on_exception():
    """Test that main() returns a non-zero exit code when a tool raises an exception.

    This test verifies that run_tool.main() is wrapped in sys.exit() so that
    exceptions properly result in non-zero exit codes.
    """
    with patch("sys.argv", ["run.py", "train", "nonexistent_recipe_that_does_not_exist"]):
        exit_code = main()

    # The process should exit with a non-zero code (error), not 0 (success)
    # Exit code 1 = tool invocation failed, 2 = usage error
    assert exit_code != 0, f"Expected non-zero exit code for failed tool invocation, got {exit_code}"


def test_run_tool_returns_exit_code_0_on_success():
    """Test that main() returns exit code 0 when a tool succeeds."""
    with patch("sys.argv", ["run.py", "train", "cogsguard", "--dry-run"]):
        exit_code = main()

    assert exit_code == 0, f"Expected exit code 0 for successful tool invocation, got {exit_code}"
