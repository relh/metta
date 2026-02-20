from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from devops.stable.function_checks._helpers.isolated_venv import (
    run_command_in_venv,
    run_commands_in_isolated_venv,
)


class _FakeTempDir:
    def __init__(self, path: Path):
        self._path = path

    def __enter__(self) -> str:
        return str(self._path)

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = (exc_type, exc, tb)


def test_run_commands_in_isolated_venv_runs_expected_commands(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []
    fake_temp_dir_root = tmp_path / "smoke"

    def _fake_temp_dir(*, prefix: str):
        _ = prefix
        return _FakeTempDir(fake_temp_dir_root)

    def _fake_run(
        cmd: list[str],
        *,
        check: bool,
        capture_output: bool = False,
        text: bool = True,
    ):
        assert check is True
        _ = (capture_output, text)
        commands.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", _fake_temp_dir)
    monkeypatch.setattr("subprocess.run", _fake_run)

    run_commands_in_isolated_venv(
        packages=["cogames"],
        commands=[["cogames", "version"]],
        python_executable="python3",
        tmp_dir_prefix="cogames_smoke_",
    )

    venv_dir = fake_temp_dir_root / "venv"
    assert commands == [
        ["python3", "-m", "venv", str(venv_dir)],
        [str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip"],
        [str(venv_dir / "bin" / "python"), "-m", "pip", "install", "cogames"],
        [str(venv_dir / "bin" / "cogames"), "version"],
    ]


def test_run_command_in_venv_requires_non_empty_command(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        bin_dir = Path(temp_dir) / "venv" / "bin"
        bin_dir.mkdir(parents=True)

        try:
            run_command_in_venv(bin_dir=bin_dir, command=[], check=True)
        except ValueError as exc:
            assert "non-empty" in str(exc)
        else:
            raise AssertionError("Expected ValueError for empty command")
