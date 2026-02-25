#!/usr/bin/env -S uv run

"""Training performance benchmark.

Measures training SPS and timing breakdowns using MicrobenchReporter, with
preset configs, baseline comparison, and scorecard integration.

Usage:
    # Quick local benchmark (requires GPU)
    uv run python scripts/training_perf_benchmark.py --preset quick

    # Stable measurement with baseline comparison
    uv run python scripts/training_perf_benchmark.py --preset standard \\
        --phase baseline --output results/baseline.json
    uv run python scripts/training_perf_benchmark.py --preset standard \\
        --phase opt1 --output results/opt1.json --baseline results/baseline.json

    # Custom recipe
    uv run python scripts/training_perf_benchmark.py \\
        --recipe recipes.experiment.cogsguard --recipe-fn train \\
        --total-timesteps 2000000

    # Smoke test (no GPU needed)
    uv run python scripts/training_perf_benchmark.py --preset smoke

    # Generate phase summary from results directory
    uv run python scripts/training_perf_benchmark.py --report results/
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import sys
from pathlib import Path

from metta.perf.training_harness import (
    PRESET_CONFIGS,
    best_effort_git_info,
    compare_multiple,
    compute_training_statistics,
    configure_for_benchmark,
    generate_phase_report,
    load_artifact,
    load_preset,
    print_comparison,
    print_phase_breakdown,
    print_scorecard_row,
    save_results,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Training performance benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            [
                "Preset configs (--preset):",
                *(f"  {name:<14} {p.description}" for name, p in PRESET_CONFIGS.items()),
                "",
                "Note: 'smoke' is the only CPU-safe preset. Others require a GPU.",
            ]
        ),
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--preset", choices=list(PRESET_CONFIGS.keys()), help="Use a preset config")
    source.add_argument("--recipe", help="Recipe module path (e.g. recipes.experiment.cogsguard)")
    source.add_argument("--report", help="Generate phase summary from results directory and exit")

    parser.add_argument("--recipe-fn", default="train", help="Recipe function name (default: train)")
    parser.add_argument("--run", default=None, help="Run name (default: training-bench-<timestamp>)")
    parser.add_argument("--total-timesteps", type=int, default=None, help="Override total timesteps")
    parser.add_argument("--warmup-epochs", type=int, default=None, help="Warmup epochs excluded from summary")
    parser.add_argument("--vectorization", choices=["serial", "multiprocessing"], default=None)
    parser.add_argument("--num-workers", type=int, default=None, help="Number of env workers")
    parser.add_argument("--print-per-epoch", action="store_true", help="Log per-epoch microbench metrics")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--baseline", nargs="+", help="Compare against baseline JSON file(s)")
    parser.add_argument("--phase", default="", help="Label for this optimization phase")
    args = parser.parse_args()

    # --report mode: generate summary and exit.
    if args.report:
        generate_phase_report(args.report)
        return 0

    # Deferred import to avoid torch init until we actually need it.
    from metta.rl.torch_init import configure_torch_globally_for_performance  # noqa: PLC0415

    configure_torch_globally_for_performance()

    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_name = args.run or f"training-bench-{ts}"

    # Load recipe.
    if args.preset:
        preset = PRESET_CONFIGS[args.preset]
        tool = load_preset(args.preset)
        warmup_epochs = args.warmup_epochs if args.warmup_epochs is not None else preset.warmup_epochs
        config_label = f"training ({args.preset})"
        config_info: dict = {
            "preset": args.preset,
            "total_timesteps": preset.total_timesteps,
        }
    else:
        module = importlib.import_module(args.recipe)
        maker = getattr(module, args.recipe_fn)
        tool = maker()
        warmup_epochs = args.warmup_epochs if args.warmup_epochs is not None else 2
        config_label = f"training ({args.recipe}:{args.recipe_fn})"
        config_info = {
            "recipe": args.recipe,
            "recipe_fn": args.recipe_fn,
        }

    # Apply CLI overrides.
    if args.total_timesteps is not None:
        tool.trainer.total_timesteps = args.total_timesteps
        config_info["total_timesteps"] = args.total_timesteps
    if args.vectorization is not None:
        tool.training_env.vectorization = args.vectorization
    if args.num_workers is not None:
        tool.training_env.num_workers = args.num_workers
        tool.training_env.auto_workers = False

    # Determine artifact path.
    artifact_path = Path(tool.system.data_dir) / run_name / "microbench.json"

    # Build run metadata.
    git_info = best_effort_git_info()
    run_metadata: dict = {
        "run": run_name,
        "total_timesteps": tool.trainer.total_timesteps,
        **config_info,
        **(git_info.model_dump() if git_info else {}),
    }

    # Configure for benchmarking (sets tool.run = run_name).
    configure_for_benchmark(
        tool,
        run_name=run_name,
        output_path=artifact_path,
        warmup_epochs=warmup_epochs,
        print_per_epoch=args.print_per_epoch,
        run_metadata=run_metadata,
    )

    print(f"Run: {run_name}")
    print(f"Config: {config_label}")
    print(f"Timesteps: {tool.trainer.total_timesteps:,}")
    print(f"Warmup epochs: {warmup_epochs}")
    if args.phase:
        print(f"Phase: {args.phase}")

    # apply_defaults_and_mutations sees tool.run already set → run_from_cli=False,
    # which is safe for multi-policy recipes.
    tool.apply_defaults_and_mutations({"run": run_name})

    # Save config snapshot.
    config_snapshot_path = artifact_path.with_name("microbench_config.json")
    config_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    config_snapshot_path.write_text(json.dumps(tool.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")

    exit_code = tool.invoke({"run": run_name}) or 0
    if exit_code != 0:
        print(f"\nTraining exited with code {exit_code}", file=sys.stderr)
        return int(exit_code)

    # Post-process artifact.
    artifact = load_artifact(artifact_path)
    stats = compute_training_statistics(artifact)

    print(f"\n{'=' * 60}")
    print("Training Benchmark Results")
    print(f"{'=' * 60}")
    print(f"  SPS: {stats.sps_mean:,.0f} +/- {stats.sps_std:,.0f}")
    print(f"  Median SPS: {stats.sps_median:,.0f}")
    print(f"  P10-P90: {stats.sps_p10:,.0f} - {stats.sps_p90:,.0f}")
    print(f"  Epochs: {stats.epochs} (after warmup)")
    print(f"  Stability: {stats.stability}")

    print_phase_breakdown(stats)

    if args.output:
        output_path = Path(args.output)
        save_results(stats, config_info, args.phase, output_path)

    if args.baseline:
        print(f"\n{'=' * 60}")
        print("Comparisons")
        print(f"{'=' * 60}")
        baseline_paths = [Path(p) for p in args.baseline]
        comparisons = compare_multiple(baseline_paths, stats, args.phase or "current")
        for comparison in comparisons:
            print_comparison(comparison)

    print_scorecard_row(
        stats,
        config_label=config_label,
        phase=args.phase,
        baseline_paths=[Path(p) for p in args.baseline] if args.baseline else None,
        output_path=Path(args.output) if args.output else None,
    )

    if stats.cv > 0.20:
        print("\nPerformance measurement unstable!", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
