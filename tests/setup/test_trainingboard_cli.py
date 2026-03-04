from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from metta.setup import metta_cli
from metta.setup.metta_cli import app

pytestmark = pytest.mark.setup

runner = CliRunner(mix_stderr=False)


def test_trainingboard_command_defaults_to_serve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(cmd, cwd, check):
        calls.append({"cmd": cmd, "cwd": cwd, "check": check})
        return None

    monkeypatch.setattr(metta_cli, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(metta_cli.subprocess, "run", fake_run)

    result = runner.invoke(app, ["trainingboard"])

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is False
    assert call["cmd"] == [
        "uv",
        "run",
        "--project",
        str(tmp_path / "trainingboard"),
        "trainingboard",
        "serve",
    ]


def test_trainingboard_command_passes_through_args(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(cmd, cwd, check):
        calls.append({"cmd": cmd, "cwd": cwd, "check": check})
        return None

    monkeypatch.setattr(metta_cli, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(metta_cli.subprocess, "run", fake_run)

    result = runner.invoke(app, ["trainingboard", "ingest-asana", "--project-gid", "123"])

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is False
    assert call["cmd"] == [
        "uv",
        "run",
        "--project",
        str(tmp_path / "trainingboard"),
        "trainingboard",
        "ingest-asana",
        "--project-gid",
        "123",
    ]
