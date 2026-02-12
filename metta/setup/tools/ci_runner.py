"""CI runner for local testing that matches remote CI behavior.

This tool is the single source of truth for CI checks.
Both local development (metta ci) and GitHub Actions call this same tool.

GitHub Actions workflow calls individual stages:
  - metta ci lint
  - metta ci python-tests
  - metta ci cpp-tests
  - metta ci cpp-benchmarks
  - metta ci nim-tests
  - metta ci recipe-tests
  - metta ci cogames-docsync

Local development can run all default stages:
  - metta ci

Extra arguments are passed through to the underlying command:
  - metta ci python-tests --skip-package app_backend
  - metta ci recipe-tests --job some_filter
"""

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Sequence

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from metta.common.util.fs import get_repo_root
from metta.setup.utils import error, info, success

console = Console()


@dataclass(frozen=True)
class Stage:
    name: str
    display: str
    cmd: list[str] = field(default_factory=list)
    default: bool = True


STAGES: list[Stage] = [
    Stage(
        name="lint",
        display="Lint",
        cmd=["uv", "run", "metta", "lint"],
    ),
    Stage(
        name="python-tests",
        display="Python Tests",
        cmd=["uv", "run", "metta", "pytest", "--ci", "--test"],
    ),
    Stage(
        name="cpp-tests",
        display="C++ Tests",
        cmd=["uv", "run", "metta", "cpptest", "--test"],
    ),
    Stage(
        name="cpp-benchmarks",
        display="C++ Benchmarks",
        cmd=["uv", "run", "metta", "cpptest", "--benchmark"],
    ),
    Stage(
        name="nim-tests",
        display="Nim Tests",
        cmd=["uv", "run", "metta", "nimtest"],
    ),
    Stage(
        name="recipe-tests",
        display="Recipe Tests",
        cmd=["uv", "run", "./devops/stable/cli.py", "--suite=ci", "--skip-submitting-metrics"],
    ),
    Stage(
        name="cogames-docsync",
        display="CoGames Docsync",
        cmd=["uv", "run", "cogames", "docsync", "check"],
        default=False,
    ),
    Stage(
        name="cleanup-cancelled-runs",
        display="Cleanup Cancelled Runs",
        cmd=["uv", "run", ".github/actions/cleanup-cancelled-runs/cleanup_cancelled_runs.py"],
        default=False,
    ),
]

STAGE_MAP: dict[str, Stage] = {s.name: s for s in STAGES}


def _run_command(cmd: Sequence[str], description: str, *, verbose: bool = False) -> bool:
    display_cmd = shlex.join(cmd)
    info(f"Running: {display_cmd}")

    in_ci = bool(os.environ.get("CI"))
    capture = not verbose and not in_ci

    proc = subprocess.run(
        cmd,
        cwd=get_repo_root(),
        capture_output=capture,
        text=True,
    )

    passed = proc.returncode == 0

    if capture and not passed:
        if proc.stdout:
            console.print(proc.stdout, markup=False)
        if proc.stderr:
            console.print(proc.stderr, markup=False)

    if passed:
        success(f"{description} passed")
    else:
        error(f"{description} failed")

    return passed


def _run_stage(stage: Stage, extra_args: Sequence[str] = (), *, verbose: bool = False) -> tuple[str, bool]:
    console.print(f"\n[bold cyan]{stage.display}[/bold cyan]")
    console.print("=" * 60)
    cmd = [*stage.cmd, *extra_args]
    passed = _run_command(cmd, stage.display, verbose=verbose)
    return stage.display, passed


def _print_summary(results: list[tuple[str, bool]]) -> None:
    console.print()

    table = Table(title="CI Check Summary", show_header=True, header_style="bold magenta")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")

    for name, passed in results:
        status = "[green]PASSED[/green]" if passed else "[red]FAILED[/red]"
        table.add_row(name, status)

    console.print(table)
    console.print()


def cmd_ci(
    ctx: typer.Context,
    stage: str | None = typer.Argument(None, help=f"Stage to run: {', '.join(STAGE_MAP)}"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    continue_on_error: bool = typer.Option(False, "--continue-on-error", help="Don't stop on first failure"),
):
    """Run CI checks locally to match remote CI behavior."""
    extra_args = ctx.args

    if extra_args and stage is None:
        error("Extra arguments require specifying a stage.")
        raise typer.Exit(1)

    if stage:
        if stage not in STAGE_MAP:
            error(f"Unknown stage: {stage}")
            info(f"Valid stages: {', '.join(STAGE_MAP)}")
            raise typer.Exit(1)

        _name, passed = _run_stage(STAGE_MAP[stage], extra_args, verbose=verbose)
        if passed:
            success(f"Stage '{stage}' passed!")
            sys.exit(0)
        else:
            error(f"Stage '{stage}' failed.")
            sys.exit(1)

    console.print(Panel.fit("[bold]Running All CI Checks[/bold]", border_style="cyan"))

    results: list[tuple[str, bool]] = []

    for s in STAGES:
        if not s.default:
            continue
        name, passed = _run_stage(s, verbose=verbose)
        results.append((name, passed))
        if not passed and not continue_on_error:
            _print_summary(results)
            error(f"Stage '{s.name}' failed. Fix errors and try again.")
            raise typer.Exit(1)

    _print_summary(results)

    all_passed = all(passed for _, passed in results)
    if all_passed:
        success("All CI checks passed!")
        sys.exit(0)
    else:
        error("Some CI checks failed.")
        sys.exit(1)
