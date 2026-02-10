#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import importlib.util
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from metta.abtest.experiment import ABExperiment, ABRun, materialize_runs


@dataclass(frozen=True)
class LaunchConfig:
    skypilot: bool
    dry_run: bool
    parallel: int
    gpus: int | None
    nodes: int | None
    cpus: int | None
    spot: bool
    max_runtime_hours: float | None


def _load_experiment(file_path: Path) -> ABExperiment:
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load experiment file: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]

    fn = getattr(module, "experiment", None)
    if not callable(fn):
        raise ValueError("experiment file must define an `experiment()` function returning an ABExperiment")

    exp = fn()
    if not isinstance(exp, ABExperiment):
        raise TypeError(f"experiment() must return ABExperiment, got {type(exp).__name__}")
    return exp


def _cmd_for_run(run: ABRun, tool_tokens: list[str], cfg: LaunchConfig) -> list[str]:
    if cfg.skypilot:
        cmd: list[str] = ["uv", "run", "--active", "devops/skypilot/launch.py"]
        cmd.extend(tool_tokens)
        if cfg.gpus is not None:
            cmd.extend(["--gpus", str(cfg.gpus)])
        if cfg.nodes is not None:
            cmd.extend(["--nodes", str(cfg.nodes)])
        if cfg.cpus is not None:
            cmd.extend(["--cpus", str(cfg.cpus)])
        if cfg.max_runtime_hours is not None:
            cmd.extend(["--max-runtime-hours", str(cfg.max_runtime_hours)])
        if cfg.spot:
            cmd.append("--spot")
        if cfg.dry_run:
            cmd.append("--dry-run")
        cmd.append("--")
        cmd.extend(run.args)
        return cmd

    cmd = ["uv", "run", "--active", "tools/run.py"]
    cmd.extend(tool_tokens)
    if cfg.dry_run:
        cmd.append("--dry-run")
    cmd.extend(run.args)
    return cmd


def _print_cmd(cmd: list[str]) -> None:
    print(" ".join([subprocess.list2cmdline([c]) if " " in c else c for c in cmd]))


def _run_one(cmd: list[str]) -> int:
    proc = subprocess.run(cmd)
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_file", type=Path, help="Path to a python file that defines experiment()")
    parser.add_argument("--skypilot", action="store_true", help="Launch each run via devops/skypilot/launch.py")
    parser.add_argument("--dry-run", action="store_true", help="Print commands only (no execution)")
    parser.add_argument("--parallel", type=int, default=1, help="Number of concurrent runs (local mode only)")
    parser.add_argument("--gpus", type=int, default=None)
    parser.add_argument("--nodes", type=int, default=None)
    parser.add_argument("--cpus", type=int, default=None)
    parser.add_argument("--spot", action="store_true")
    parser.add_argument("--max-runtime-hours", type=float, default=None)
    args = parser.parse_args(argv)

    exp = _load_experiment(args.experiment_file)
    runs = materialize_runs(exp)
    tool_tokens = list(exp.tool)

    cfg = LaunchConfig(
        skypilot=bool(args.skypilot),
        dry_run=bool(args.dry_run),
        parallel=max(1, int(args.parallel)),
        gpus=args.gpus,
        nodes=args.nodes,
        cpus=args.cpus,
        spot=bool(args.spot),
        max_runtime_hours=args.max_runtime_hours,
    )

    commands = [_cmd_for_run(r, tool_tokens, cfg) for r in runs]
    for cmd in commands:
        _print_cmd(cmd)

    if cfg.dry_run:
        return 0

    if cfg.skypilot:
        # Skypilot launch includes interactive confirmation if enabled; keep sequential.
        for cmd in commands:
            rc = _run_one(cmd)
            if rc != 0:
                return rc
        return 0

    # Local execution: optional parallelism.
    with ThreadPoolExecutor(max_workers=cfg.parallel) as ex:
        futs = [ex.submit(_run_one, cmd) for cmd in commands]
        for fut in as_completed(futs):
            rc = fut.result()
            if rc != 0:
                return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
