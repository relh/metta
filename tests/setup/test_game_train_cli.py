from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from metta.setup import metta_cli
from metta.setup.metta_cli import app

pytestmark = pytest.mark.setup

runner = CliRunner(mix_stderr=False)


def test_train_game_command_routes_to_game_recipe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    def fake_run(cmd, cwd, check):
        calls.append({"cmd": cmd, "cwd": cwd, "check": check})
        return None

    monkeypatch.setattr(metta_cli, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(metta_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(metta_cli, "resolve_and_load_tool_maker", lambda _: None)

    result = runner.invoke(
        app,
        ["train", "hunger", "trainer.total_timesteps=12345"],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is True
    assert call["cmd"][0] == metta_cli.sys.executable
    assert call["cmd"][1] == str(tmp_path / "tools" / "run.py")
    assert call["cmd"][2:] == ["game.train", "game=hunger", "trainer.total_timesteps=12345"]


def test_train_command_routes_to_standalone_recipe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    def fake_run(cmd, cwd, check):
        calls.append({"cmd": cmd, "cwd": cwd, "check": check})
        return None

    monkeypatch.setattr(metta_cli, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(metta_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        metta_cli,
        "resolve_and_load_tool_maker",
        lambda path: object() if path == "cogsguard.train" else None,
    )

    result = runner.invoke(
        app,
        ["train", "cogsguard", "trainer.total_timesteps=12345"],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is True
    assert call["cmd"][0] == metta_cli.sys.executable
    assert call["cmd"][1] == str(tmp_path / "tools" / "run.py")
    assert call["cmd"][2:] == ["cogsguard.train", "trainer.total_timesteps=12345"]


def test_train_command_accepts_game_prefix_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    def fake_run(cmd, cwd, check):
        calls.append({"cmd": cmd, "cwd": cwd, "check": check})
        return None

    monkeypatch.setattr(metta_cli, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(metta_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(metta_cli, "resolve_and_load_tool_maker", lambda _: None)

    result = runner.invoke(
        app,
        ["train", "game.hunger", "trainer.total_timesteps=12345"],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is True
    assert call["cmd"][0] == metta_cli.sys.executable
    assert call["cmd"][1] == str(tmp_path / "tools" / "run.py")
    assert call["cmd"][2:] == ["game.train", "game=hunger", "trainer.total_timesteps=12345"]
