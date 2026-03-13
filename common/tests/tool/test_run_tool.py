"""Integration tests for run_tool main() focusing on user-facing behavior."""

import os
import sys

import pytest

from metta.common.tests_support import run_tool_in_process
from metta.common.tool import run_tool as run_tool_module
from metta.common.tool.recipe_registry import recipe_registry


@pytest.fixture
def with_extra_imports_root(monkeypatch):
    """Add test fixtures to Python path for recipe/tool discovery."""
    extra_imports_root = os.path.join(os.path.dirname(__file__), "fixtures/extra-import-root")
    monkeypatch.setenv("PYTHONPATH", extra_imports_root)
    monkeypatch.syspath_prepend(extra_imports_root)

    # Clear cached imports and recipe registry to prevent CI flakiness
    # when tests are retried or run in parallel (Datadog retries, pytest-xdist)
    test_modules = [k for k in sys.modules if k.startswith("mypackage")]
    for mod_name in test_modules:
        sys.modules.pop(mod_name, None)
    recipe_registry.clear()


@pytest.fixture
def invoke_run_tool(monkeypatch, capsys, with_extra_imports_root):  # noqa: ANN001
    """Fixture that invokes run_tool.main() in-process."""

    def _invoke(*args: str):
        return run_tool_in_process(*args, monkeypatch=monkeypatch, capsys=capsys, argv0="run_tool.py")

    return _invoke


# --------------------------------------------------------------------------------------
# Basic Tool Loading and Execution
# --------------------------------------------------------------------------------------


def test_tool_class_loads_and_invokes(invoke_run_tool):
    """Verify a Tool class can be loaded and invoked successfully."""
    result = invoke_run_tool("mypackage.tools.TestTool")

    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "TestTool invoked" in output


def test_unknown_tool_fails_with_error(invoke_run_tool):
    """Verify attempting to load a non-existent tool produces an error."""
    result = invoke_run_tool("mypackage.tools.NoSuchTool")

    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "NoSuchTool" in output


def test_unknown_module_fails_with_error(invoke_run_tool):
    """Verify attempting to load from a non-existent module produces an error."""
    result = invoke_run_tool("mypackage.no_such_module.TestTool")

    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "no_such_module" in output


# --------------------------------------------------------------------------------------
# Argument Handling
# --------------------------------------------------------------------------------------


def test_required_field_can_be_provided(invoke_run_tool):
    """Verify required Pydantic fields can be provided via CLI and are used."""
    result = invoke_run_tool("mypackage.tools.RequiredFieldTool", "x=123")

    assert result.returncode == 0
    output = result.stdout + result.stderr
    # Tool prints the value of x
    assert "123" in output


def test_nested_config_overrides_applied(invoke_run_tool):
    """Verify dotted CLI arguments override nested configuration fields."""
    result = invoke_run_tool(
        "mypackage.tools.SimpleTestTool",
        "value=custom",
        "nested.field=updated",
        "nested.another_field=999",
    )

    assert result.returncode == 0
    output = result.stdout + result.stderr
    # Tool prints these values in invoke()
    assert "Tool value: custom" in output
    assert "Tool nested.field: updated" in output
    assert "Tool nested.another_field: 999" in output


def test_literal_none_override_is_applied_as_string(invoke_run_tool):
    """Verify `field=none` can target Literal fields that include the string "none"."""
    result = invoke_run_tool("mypackage.tools.LiteralNoneTool", "render=none")

    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "render=none" in output


def test_function_params_passed_to_invoke(invoke_run_tool):
    """Verify function parameters are bound and passed to invoke() as args."""
    result = invoke_run_tool(
        "mypackage.tools.make_test_tool",
        "run=my_test",
        "count=99",
        "settings.field=from_function_param",
        "settings.another_field=11",
        "value=override",
    )

    assert result.returncode == 0
    output = result.stdout + result.stderr
    # Function params (run, count) are passed to invoke() as strings
    assert "'run': 'my_test'" in output
    assert "'count': '99'" in output
    # Config overrides (value) affect the tool instance
    assert "Tool value: override" in output
    assert "Tool nested.field: from_function_param" in output
    assert "Tool nested.another_field: 11" in output


# --------------------------------------------------------------------------------------
# Recipe Tool Discovery
# --------------------------------------------------------------------------------------


def test_two_token_form_resolves_correctly(invoke_run_tool):
    """Verify two-token syntax 'x y' resolves to 'y.x'."""
    # Use --dry-run to avoid needing to actually run the tool
    result = invoke_run_tool("make_test_tool", "mypackage.tools", "--dry-run")

    assert result.returncode == 0


def test_print_effective_config_prints_prepared_config(invoke_run_tool):
    result = invoke_run_tool("mypackage.tools.EffectiveConfigTool", "--print-effective-config")
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert '"x": 2' in output
    assert "x=1" not in output


def test_tool_preparation_runs_before_invoke(invoke_run_tool):
    result = invoke_run_tool("mypackage.tools.EffectiveConfigTool")
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "x=2" in output


def test_two_token_not_treated_as_bare_tool(invoke_run_tool):
    """Verify two-token form 'tool recipe' is not treated as bare tool.

    Regression test for: when running './tools/run.py train ci --help',
    it should show help for that specific tool, not list all train implementations.
    """
    # This should show help for the specific tool, not list all 'evaluate' implementations
    result = invoke_run_tool("evaluate", "mypackage.recipes.demo", "--help")

    assert result.returncode == 0
    output = result.stdout + result.stderr

    # Should NOT show "Available 'evaluate' implementations:" (bare tool behavior)
    assert "Available 'evaluate' implementations:" not in output
    # Should show help for the specific tool instead
    assert "Available Arguments" in output or "Function Parameters" in output


def test_compat_version_dispatches_before_tool_resolution(monkeypatch, capsys, with_extra_imports_root):  # noqa: ANN001
    called: dict[str, str] = {}

    def _fake_run_in_compat_version(version: str) -> int:
        called["version"] = version
        return 23

    monkeypatch.setattr(run_tool_module, "_run_in_compat_version", _fake_run_in_compat_version)

    result = run_tool_in_process(
        "--compat-version",
        "0.18",
        "mypackage.tools.NoSuchTool",
        monkeypatch=monkeypatch,
        capsys=capsys,
        argv0="run_tool.py",
    )

    assert result.returncode == 23
    assert called["version"] == "0.18"


# --------------------------------------------------------------------------------------
# Tool Listing
# --------------------------------------------------------------------------------------


def test_list_shows_explicit_tools(invoke_run_tool):
    """Verify --list displays explicitly defined tools."""
    result = invoke_run_tool("mypackage.recipes.demo", "--list")

    assert result.returncode == 0
    output = result.stdout + result.stderr

    # Should show the recipe module name
    assert "mypackage.recipes.demo" in output

    # Should include explicit tool-returning function
    assert "train_shaped" in output


# --------------------------------------------------------------------------------------
# Error Handling
# --------------------------------------------------------------------------------------


def test_missing_required_field_fails(invoke_run_tool):
    """Verify missing required field causes validation error."""
    result = invoke_run_tool("mypackage.tools.RequiredFieldTool")

    assert result.returncode != 0


def test_unknown_argument_produces_error(invoke_run_tool):
    """Verify unknown arguments are reported to user."""
    result = invoke_run_tool(
        "mypackage.tools.SimpleTestTool",
        "value=test",
        "unknown_field=value",
    )

    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "unknown_field" in output
