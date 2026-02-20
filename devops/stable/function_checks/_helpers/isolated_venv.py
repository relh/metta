from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def isolated_venv(
    *,
    packages: list[str],
    tmp_dir_prefix: str = "",
    python_executable: str = "python3",
) -> Iterator[Path]:
    """Create a temporary virtualenv, install packages, and yield its bin directory."""
    with tempfile.TemporaryDirectory(prefix=tmp_dir_prefix) as temp_dir:
        venv_dir = Path(temp_dir) / "venv"
        venv_bin_dir = venv_dir / "bin"
        venv_python = venv_dir / "bin" / "python"

        subprocess.run([python_executable, "-m", "venv", str(venv_dir)], check=True)
        subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        if len(packages) > 0:
            subprocess.run([str(venv_python), "-m", "pip", "install", *packages], check=True)

        yield venv_bin_dir


def run_command_in_venv(
    *,
    bin_dir: Path,
    command: list[str],
    check: bool,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command using executables from a provided virtualenv bin directory."""
    if len(command) == 0:
        raise ValueError("command must be non-empty")
    resolved_command = [str(bin_dir / command[0]), *command[1:]]
    return subprocess.run(
        resolved_command,
        check=check,
        capture_output=capture_output,
        text=text,
    )


def run_commands_in_isolated_venv(
    *,
    packages: list[str],
    commands: list[list[str]],
    tmp_dir_prefix: str = "",
    python_executable: str = "python3",
) -> list[subprocess.CompletedProcess[str]]:
    """Create an isolated venv and run a sequence of commands inside it."""
    results: list[subprocess.CompletedProcess[str]] = []
    with isolated_venv(
        packages=packages,
        python_executable=python_executable,
        tmp_dir_prefix=tmp_dir_prefix,
    ) as bin_dir:
        for command in commands:
            results.append(
                run_command_in_venv(
                    bin_dir=bin_dir,
                    command=command,
                    check=True,
                    capture_output=False,
                )
            )
    return results
