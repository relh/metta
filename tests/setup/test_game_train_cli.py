from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from metta.setup import metta_cli
from metta.setup.metta_cli import app

pytestmark = pytest.mark.setup

runner = CliRunner(mix_stderr=False)


def _invoke_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argv: list[str],
    *,
    resolver: Callable[[str], object | None],
) -> tuple[Result, list[dict[str, object]]]:
    calls: list[dict[str, object]] = []

    def fake_run(cmd, cwd, check):
        calls.append({"cmd": cmd, "cwd": cwd, "check": check})
        return None

    monkeypatch.setattr(metta_cli, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(metta_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(metta_cli, "resolve_and_load_tool_maker", resolver)

    result = runner.invoke(app, argv)
    return result, calls


def test_train_game_command_routes_to_game_recipe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["train", "hunger", "trainer.total_timesteps=12345"],
        resolver=lambda path: object() if path == "hunger.train" else None,
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is True
    assert call["cmd"][0] == metta_cli.sys.executable
    assert call["cmd"][1] == str(tmp_path / "tools" / "run.py")
    assert call["cmd"][2:] == ["hunger.train", "trainer.total_timesteps=12345"]


def test_train_command_routes_to_standalone_recipe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["train", "cogsguard", "trainer.total_timesteps=12345"],
        resolver=lambda path: object() if path == "cogsguard.train" else None,
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
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["train", "game.hunger", "trainer.total_timesteps=12345"],
        resolver=lambda path: object() if path == "hunger.train" else None,
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is True
    assert call["cmd"][0] == metta_cli.sys.executable
    assert call["cmd"][1] == str(tmp_path / "tools" / "run.py")
    assert call["cmd"][2:] == ["hunger.train", "trainer.total_timesteps=12345"]


def test_train_cogs_vs_clips_recipe_accepts_env_name_arg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["train", "cogs_vs_clips", "env_name=cogsguard_8agents", "trainer.total_timesteps=12345"],
        resolver=lambda path: object() if path == "cogs_vs_clips.train" else None,
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is True
    assert call["cmd"][0] == metta_cli.sys.executable
    assert call["cmd"][1] == str(tmp_path / "tools" / "run.py")
    assert call["cmd"][2:] == ["cogs_vs_clips.train", "env_name=cogsguard_8agents", "trainer.total_timesteps=12345"]


def test_play_cogs_vs_clips_recipe_accepts_env_name_arg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["play", "cogs_vs_clips", "env_name=cogsguard_8agents", "max_steps=123"],
        resolver=lambda path: object() if path == "cogs_vs_clips.play" else None,
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["cwd"] == tmp_path
    assert call["check"] is True
    assert call["cmd"][0] == metta_cli.sys.executable
    assert call["cmd"][1] == str(tmp_path / "tools" / "run.py")
    assert call["cmd"][2:] == ["cogs_vs_clips.play", "env_name=cogsguard_8agents", "max_steps=123"]


def test_train_unknown_game_fails_fast(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["train", "not_a_real_game"],
        resolver=lambda _: None,
    )

    assert result.exit_code == 2
    assert not calls
    assert "Unknown game 'not_a_real_game'" in result.stderr


def test_train_tournament_env_name_requires_explicit_recipe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["train", "cogsguard_8agents"],
        resolver=lambda _: None,
    )

    assert result.exit_code == 2
    assert not calls
    assert "Unknown game 'cogsguard_8agents'" in result.stderr


def test_play_tournament_env_name_requires_explicit_recipe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result, calls = _invoke_cli(
        monkeypatch,
        tmp_path,
        ["play", "cogsguard_8agents"],
        resolver=lambda _: None,
    )

    assert result.exit_code == 2
    assert not calls
    assert "Unknown game 'cogsguard_8agents'" in result.stderr
