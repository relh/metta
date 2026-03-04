#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path

from metta.cogworks.curriculum import Curriculum
from metta.common.wandb.context import WandbConfig
from metta.rl.torch_init import configure_torch_globally_for_performance
from metta.rl.training import MicrobenchReporter, MicrobenchReporterConfig
from metta.rl.training.batch import calculate_batch_sizes
from recipes.experiment import cogsguard


def _best_effort_git_info() -> dict[str, str]:
    def _run(*args: str) -> str | None:
        if shutil.which("git") is None:
            return None
        proc = subprocess.run(
            ["git", *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    info: dict[str, str] = {}
    head = _run("rev-parse", "HEAD")
    if head:
        info["git_head"] = head
    branch = _run("branch", "--show-current")
    if branch:
        info["git_branch"] = branch
    return info


def _largest_divisor_at_most(target: int, limit: int) -> int:
    for divisor in range(min(target, limit), 0, -1):
        if target % divisor == 0:
            return divisor
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Microbench Cogsguard training SPS and timing breakdowns.")
    parser.add_argument("--run", default=None, help="Run name (default: microbench-cogsguard-<timestamp>)")
    parser.add_argument(
        "--layout",
        choices=["machina_1", "arena"],
        default="machina_1",
        help="CogsGuard layout to benchmark.",
    )
    parser.add_argument(
        "--variants",
        default=None,
        help="Comma-separated mission variants (default: recipe default). Example: milestones,credit",
    )
    parser.add_argument("--total-timesteps", type=int, default=1_000_000, help="Total agent timesteps to run.")
    parser.add_argument("--update-epochs", type=int, default=1, help="PPO update epochs per rollout batch.")
    parser.add_argument("--warmup-epochs", type=int, default=2, help="Warmup epochs excluded from summary.")
    parser.add_argument("--vectorization", choices=["serial", "multiprocessing"], default="multiprocessing")
    parser.add_argument("--num-workers", type=int, default=1, help="Number of env workers (multiprocessing only).")
    parser.add_argument("--async-factor", type=int, default=2, help="Async factor (multiprocessing only).")
    parser.add_argument(
        "--forward-pass-minibatch-target-size",
        type=int,
        default=4096,
        help="Target forward-pass minibatch size used to size the vecenv batch.",
    )
    parser.add_argument(
        "--zero-copy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable PufferLib zero-copy mode (recommended).",
    )
    parser.add_argument(
        "--sync-traj",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable deterministic vecenv trajectory sync (can increase env wait due to head-of-line blocking).",
    )
    parser.add_argument(
        "--compile",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable torch.compile for the training step (off by default; can skew short-run microbench).",
    )
    parser.add_argument(
        "--compile-mode",
        choices=["default", "reduce-overhead", "max-autotune"],
        default="reduce-overhead",
        help="torch.compile mode (only used if --compile).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output JSON path (default: <data_dir>/<run>/microbench.json).",
    )
    parser.add_argument(
        "--print-per-epoch",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Log per-epoch microbench metrics (in addition to the normal trainer output).",
    )
    parser.add_argument(
        "--torch-profiler",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable torch.profiler trace capture (writes compressed chrome traces).",
    )
    parser.add_argument(
        "--torch-profiler-interval-epochs",
        type=int,
        default=1,
        help="Profile every N epochs (only used if --torch-profiler).",
    )
    parser.add_argument(
        "--torch-profiler-first-epoch",
        type=int,
        default=1,
        help="First epoch to profile (sets TORCH_PROFILER_FIRST_EPOCH).",
    )
    parser.add_argument(
        "--torch-profiler-active-steps",
        type=int,
        default=None,
        help="Profiler active steps (minibatch steps) per trace (default: component default).",
    )
    parser.add_argument(
        "--torch-profiler-dir",
        default=None,
        help="Profile output directory URI or path (default: file://<run_dir>/torch_profiler).",
    )
    args = parser.parse_args()

    configure_torch_globally_for_performance()

    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    run = args.run or f"microbench-cogsguard-{ts}"

    variants = None
    if args.variants:
        variants = [v.strip() for v in args.variants.split(",") if v.strip()]

    tool = cogsguard.train(layout=args.layout, variants=variants)

    # Keep the benchmark stable and avoid external services.
    tool.wandb = WandbConfig.Off()
    tool.stats_server_uri = None
    tool.group = None

    # Avoid eval/checkpoint overhead in the hot path (microbench cares about rollout+train).
    tool.evaluator.epoch_interval = 0
    tool.evaluator.evaluate_local = False
    tool.evaluator.evaluate_remote = False
    tool.policy_assets["learner0"].checkpoint = False

    tool.trainer.total_timesteps = int(args.total_timesteps)
    tool.trainer.update_epochs = int(args.update_epochs)
    tool.trainer.compile = bool(args.compile)
    tool.trainer.compile_mode = str(args.compile_mode)

    # Force explicit env parallelism to avoid auto-tuning noise.
    tool.training_env.vectorization = args.vectorization
    tool.training_env.auto_workers = False
    tool.training_env.num_workers = int(args.num_workers)
    tool.training_env.async_factor = int(args.async_factor)
    tool.training_env.forward_pass_minibatch_target_size = int(args.forward_pass_minibatch_target_size)
    tool.training_env.zero_copy = bool(args.zero_copy)
    tool.training_env.sync_traj = bool(args.sync_traj)

    # Keep trainer batch geometry aligned with selected vecenv geometry.
    # Experience requires: trainer.batch_size // bptt_horizon == total_parallel_agents.
    curriculum = Curriculum(tool.training_env.curriculum)
    num_agents = int(curriculum.get_task().get_env_cfg().game.num_agents)
    _target_batch_size, env_batch_size, num_envs = calculate_batch_sizes(
        forward_pass_minibatch_target_size=int(args.forward_pass_minibatch_target_size),
        num_agents=num_agents,
        num_workers=int(args.num_workers),
        async_factor=int(args.async_factor),
    )
    total_parallel_agents = int(num_envs * num_agents)
    bptt_horizon = int(tool.trainer.bptt_horizon)
    tool.trainer.batch_size = total_parallel_agents * bptt_horizon
    minibatch_segments = _largest_divisor_at_most(total_parallel_agents, 64)
    tool.trainer.minibatch_size = minibatch_segments * bptt_horizon

    # StatsReporter already logs SPS and timing breakdowns; ensure it doesn't attempt wandb.
    tool.stats_reporter.report_to_wandb = False
    tool.stats_reporter.interval = 1

    out_path = Path(args.out) if args.out else Path(tool.system.data_dir) / run / "microbench.json"

    if args.torch_profiler:
        # TorchProfiler defaults to profiling epoch 300; override for short microbench runs.
        os.environ["TORCH_PROFILER_FIRST_EPOCH"] = str(int(args.torch_profiler_first_epoch))

        profiler_dir = args.torch_profiler_dir
        if profiler_dir is None:
            profiler_dir = f"file://{(out_path.parent / 'torch_profiler').resolve()}"
        elif "://" not in profiler_dir:
            profiler_dir = f"file://{Path(profiler_dir).expanduser().resolve()}"

        tool.torch_profiler.interval_epochs = int(args.torch_profiler_interval_epochs)
        tool.torch_profiler.profile_dir = profiler_dir
        if args.torch_profiler_active_steps is not None:
            tool.torch_profiler.active_steps = int(args.torch_profiler_active_steps)

    run_metadata = {
        "run": run,
        "layout": args.layout,
        "variants": variants or [],
        "total_timesteps": int(args.total_timesteps),
        "update_epochs": int(args.update_epochs),
        "vectorization": args.vectorization,
        "num_workers": int(args.num_workers),
        "async_factor": int(args.async_factor),
        "forward_pass_minibatch_target_size": int(args.forward_pass_minibatch_target_size),
        "zero_copy": bool(args.zero_copy),
        "sync_traj": bool(args.sync_traj),
        "compile": bool(args.compile),
        "compile_mode": str(args.compile_mode),
        "torch_profiler": bool(args.torch_profiler),
        "num_agents": num_agents,
        "num_envs": num_envs,
        "total_parallel_agents": total_parallel_agents,
        "trainer_batch_size": int(tool.trainer.batch_size),
        "trainer_minibatch_size": int(tool.trainer.minibatch_size),
        **_best_effort_git_info(),
    }

    tool.extra_components.append(
        MicrobenchReporter(
            MicrobenchReporterConfig(
                warmup_epochs=int(args.warmup_epochs),
                output_path=out_path,
                print_per_epoch=bool(args.print_per_epoch),
            ),
            run_metadata=run_metadata,
        )
    )

    # Apply the same run/default mutations used by tools/run.py so invoke()
    # sees a concrete run name and finalized policy/checkpoint settings.
    tool.apply_defaults_and_mutations({"run": run})

    # Attach config snapshot for easier comparisons across artifacts.
    config_snapshot_path = out_path.with_name("microbench_config.json")
    config_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    config_snapshot_path.write_text(json.dumps(tool.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")

    return int(tool.invoke({"run": run}) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
