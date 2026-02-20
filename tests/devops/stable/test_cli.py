from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

import devops.stable.stable_check_cli as stable_cli
from devops.stable.stable_check_groups import StableCheckGroup

runner = CliRunner(mix_stderr=False)


def _patch_discovery(monkeypatch, captured: dict[str, Any]) -> None:
    def _discover(*, check_groups=None):  # noqa: ANN001
        captured["check_groups"] = check_groups
        return []

    monkeypatch.setattr(stable_cli, "discover_stable_checks", _discover)


def test_cli_accepts_single_check_group(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    _patch_discovery(monkeypatch, captured)

    result = runner.invoke(
        stable_cli.app,
        [
            "--check-group",
            "live_tests_light",
            "--skip-submitting-metrics",
        ],
    )

    assert result.exit_code == 1
    assert captured["check_groups"] == {StableCheckGroup.LIVE_TESTS_LIGHT}


def test_cli_accepts_repeated_check_groups(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    _patch_discovery(monkeypatch, captured)

    result = runner.invoke(
        stable_cli.app,
        [
            "--check-group",
            "live_tests_light",
            "--check-group",
            "internal_training_light",
            "--skip-submitting-metrics",
        ],
    )

    assert result.exit_code == 1
    assert captured["check_groups"] == {
        StableCheckGroup.LIVE_TESTS_LIGHT,
        StableCheckGroup.INTERNAL_TRAINING_LIGHT,
    }


def test_cli_rejects_comma_separated_check_groups(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    _patch_discovery(monkeypatch, captured)

    result = runner.invoke(
        stable_cli.app,
        [
            "--check-group",
            "live_tests_light,internal_training_light",
            "--skip-submitting-metrics",
        ],
    )

    assert result.exit_code == 2
    # Typer/Click error text formatting can vary across versions, but parsing
    # must fail before callback/discovery is invoked.
    assert "check_groups" not in captured
