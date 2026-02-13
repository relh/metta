#!/usr/bin/env python3
"""Profile logging and metrics overhead during training.

This script measures the performance overhead of various logging and metrics
components in the metta training pipeline:

1. WandB logging (run.log calls)
2. ProgressLogger console rendering
3. Metric computation (accumulate_rollout_stats, process_training_stats)
4. System/memory monitoring

Usage:
    uv run python tests/perf/profile_logging_overhead.py [--epochs N] [--output FILE]

The script patches logging components to instrument timing and outputs a
detailed breakdown of where time is spent during training.
"""

from __future__ import annotations

import argparse
import functools
import json
import logging
import os
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Add metta to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Optional imports - may not be available in all environments
try:
    import wandb

    WANDB_AVAILABLE = True
    try:
        from wandb.sdk.wandb_run import Run as WandbSdkRun  # type: ignore[import-not-found]
    except Exception:
        WandbSdkRun = None  # type: ignore[assignment]
except ImportError:
    wandb = None  # type: ignore[assignment]
    WANDB_AVAILABLE = False
    WandbSdkRun = None  # type: ignore[assignment]

try:
    from metta.common.util.log_config import init_logging
    from metta.rl import stats
    from metta.rl.training import progress_logger, stats_reporter
    from recipes.experiment import cogsguard

    METTA_AVAILABLE = True
except ImportError:
    init_logging = None  # type: ignore[assignment]
    stats = None  # type: ignore[assignment]
    progress_logger = None  # type: ignore[assignment]
    stats_reporter = None  # type: ignore[assignment]
    cogsguard = None  # type: ignore[assignment]
    METTA_AVAILABLE = False

try:
    from mettagrid.profiling import memory_monitor, system_monitor

    PROFILING_AVAILABLE = True
except ImportError:
    memory_monitor = None  # type: ignore[assignment]
    system_monitor = None  # type: ignore[assignment]
    PROFILING_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TimingStats:
    """Collect timing statistics for a single operation."""

    name: str
    call_count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float("inf")
    max_time_ms: float = 0.0
    samples: list[float] = field(default_factory=list)

    def record(self, elapsed_ms: float) -> None:
        self.call_count += 1
        self.total_time_ms += elapsed_ms
        self.min_time_ms = min(self.min_time_ms, elapsed_ms)
        self.max_time_ms = max(self.max_time_ms, elapsed_ms)
        if len(self.samples) < 1000:
            self.samples.append(elapsed_ms)

    @property
    def avg_time_ms(self) -> float:
        return self.total_time_ms / self.call_count if self.call_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "call_count": self.call_count,
            "total_time_ms": round(self.total_time_ms, 3),
            "avg_time_ms": round(self.avg_time_ms, 3),
            "min_time_ms": round(self.min_time_ms, 3) if self.min_time_ms != float("inf") else 0,
            "max_time_ms": round(self.max_time_ms, 3),
        }


class LoggingProfiler:
    """Profile logging and metrics overhead."""

    def __init__(self) -> None:
        self.stats: dict[str, TimingStats] = defaultdict(lambda: TimingStats(name="unknown"))
        self.epoch_times: list[dict[str, float]] = []
        self.start_time: float = 0.0
        self.total_agent_steps: int = 0
        self._original_funcs: dict[str, Callable] = {}

    def reset(self) -> None:
        self.stats.clear()
        self.epoch_times.clear()
        self.start_time = time.perf_counter()
        self.total_agent_steps = 0

    @contextmanager
    def time_operation(self, name: str):
        """Context manager to time an operation."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if name not in self.stats:
                self.stats[name] = TimingStats(name=name)
            self.stats[name].record(elapsed_ms)

    def wrap_function(self, name: str, func: Callable) -> Callable:
        """Wrap a function to time its execution."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self.time_operation(name):
                return func(*args, **kwargs)

        return wrapper

    def patch_wandb(self) -> None:
        """Patch W&B run logging to measure overhead."""
        if not WANDB_AVAILABLE or wandb is None:
            logger.warning("wandb not installed, skipping wandb profiling")
            return

        if WandbSdkRun is None:
            logger.warning("wandb.sdk.wandb_run.Run not importable, skipping wandb run.log profiling")
            return

        if hasattr(WandbSdkRun, "_metta_original_log"):
            return

        original_log = WandbSdkRun.log
        WandbSdkRun._metta_original_log = original_log
        self._original_funcs["wandb.Run.log"] = original_log

        @functools.wraps(original_log)
        def patched_log(self_run, *args, **kwargs):
            with self.time_operation("wandb.run.log"):
                return original_log(self_run, *args, **kwargs)

        WandbSdkRun.log = patched_log

    def patch_stats_functions(self) -> None:
        """Patch stats processing functions."""
        if not METTA_AVAILABLE or stats is None:
            logger.warning("metta.rl.stats not found, skipping stats profiling")
            return

        for name in ["accumulate_rollout_stats", "process_training_stats", "compute_timing_stats"]:
            if not hasattr(stats, name):
                continue
            original = getattr(stats, name)
            self._original_funcs[name] = original
            wrapped = self.wrap_function(name, original)
            setattr(stats, name, wrapped)

            # StatsReporter imports these names directly, so update its local bindings to
            # point at the same wrapped function (avoid double-wrapping/double-counting).
            if stats_reporter is not None and hasattr(stats_reporter, name):
                self._original_funcs[f"stats_reporter.{name}"] = getattr(stats_reporter, name)
                setattr(stats_reporter, name, wrapped)

    def patch_progress_logger(self) -> None:
        """Patch ProgressLogger."""
        if not METTA_AVAILABLE or progress_logger is None:
            logger.warning("ProgressLogger not found, skipping progress logging profiling")
            return

        if hasattr(progress_logger, "log_training_progress"):
            original = progress_logger.log_training_progress
            self._original_funcs["log_training_progress"] = original
            progress_logger.log_training_progress = self.wrap_function("log_training_progress", original)

        if hasattr(progress_logger, "log_rich_progress"):
            original = progress_logger.log_rich_progress
            self._original_funcs["log_rich_progress"] = original
            progress_logger.log_rich_progress = self.wrap_function("log_rich_progress", original)

    def patch_stats_reporter(self) -> None:
        """Patch StatsReporter methods."""
        if not METTA_AVAILABLE or stats_reporter is None:
            logger.warning("StatsReporter not found, skipping")
            return

        if hasattr(stats_reporter, "build_wandb_payload"):
            original = stats_reporter.build_wandb_payload
            self._original_funcs["build_wandb_payload"] = original
            stats_reporter.build_wandb_payload = self.wrap_function("build_wandb_payload", original)

        if hasattr(stats_reporter, "StatsReporter"):
            cls = stats_reporter.StatsReporter
            if hasattr(cls, "report_epoch"):
                original = cls.report_epoch
                self._original_funcs["StatsReporter.report_epoch"] = original

                @functools.wraps(original)
                def patched_report_epoch(self_reporter, *args, **kwargs):
                    start = time.perf_counter()
                    try:
                        return original(self_reporter, *args, **kwargs)
                    finally:
                        # report_epoch(epoch, agent_step, ...) signature; record progress for summary stats.
                        try:
                            epoch = args[0]
                            agent_step = args[1]
                        except Exception:
                            epoch = kwargs.get("epoch")
                            agent_step = kwargs.get("agent_step")
                        if epoch is not None and agent_step is not None:
                            get_profiler().record_epoch(
                                int(epoch),
                                int(agent_step),
                                epoch_time=time.perf_counter() - start,
                            )

                cls.report_epoch = patched_report_epoch

    def patch_monitor(self) -> None:
        """Patch Monitor system/memory stats collection."""
        if not PROFILING_AVAILABLE or system_monitor is None:
            logger.warning("mettagrid profiling not found, skipping monitor profiling")
            return

        # Patch SystemMonitor.stats if available
        if hasattr(system_monitor, "SystemMonitor"):
            cls = system_monitor.SystemMonitor
            if hasattr(cls, "stats"):
                original = cls.stats
                self._original_funcs["SystemMonitor.stats"] = original

                @functools.wraps(original)
                def patched_stats(self_monitor):
                    with self.time_operation("SystemMonitor.stats"):
                        return original(self_monitor)

                cls.stats = patched_stats

        if hasattr(memory_monitor, "MemoryMonitor"):
            cls = memory_monitor.MemoryMonitor
            if hasattr(cls, "stats"):
                original = cls.stats
                self._original_funcs["MemoryMonitor.stats"] = original

                @functools.wraps(original)
                def patched_mem_stats(self_monitor):
                    with self.time_operation("MemoryMonitor.stats"):
                        return original(self_monitor)

                cls.stats = patched_mem_stats

    def install_all_patches(self) -> None:
        """Install all profiling patches."""
        self.patch_wandb()
        self.patch_stats_functions()
        self.patch_progress_logger()
        self.patch_stats_reporter()
        self.patch_monitor()
        logger.info("Installed logging profiler patches")

    def restore_all(self) -> None:
        """Restore original functions."""
        if WANDB_AVAILABLE and wandb is not None:
            if WandbSdkRun is not None and hasattr(WandbSdkRun, "_metta_original_log"):
                WandbSdkRun.log = WandbSdkRun._metta_original_log
                delattr(WandbSdkRun, "_metta_original_log")

        if METTA_AVAILABLE and stats is not None:
            for name in ["accumulate_rollout_stats", "process_training_stats", "compute_timing_stats"]:
                if name in self._original_funcs:
                    setattr(stats, name, self._original_funcs[name])

        if METTA_AVAILABLE and stats_reporter is not None:
            for name in ["accumulate_rollout_stats", "process_training_stats", "compute_timing_stats"]:
                key = f"stats_reporter.{name}"
                if key in self._original_funcs:
                    setattr(stats_reporter, name, self._original_funcs[key])
            if "StatsReporter.report_epoch" in self._original_funcs and hasattr(stats_reporter, "StatsReporter"):
                stats_reporter.StatsReporter.report_epoch = self._original_funcs["StatsReporter.report_epoch"]

        if METTA_AVAILABLE and progress_logger is not None:
            for name in ["log_training_progress", "log_rich_progress"]:
                if name in self._original_funcs:
                    setattr(progress_logger, name, self._original_funcs[name])

        if METTA_AVAILABLE and stats_reporter is not None:
            if "build_wandb_payload" in self._original_funcs:
                stats_reporter.build_wandb_payload = self._original_funcs["build_wandb_payload"]

        if PROFILING_AVAILABLE:
            if "SystemMonitor.stats" in self._original_funcs and system_monitor is not None:
                if hasattr(system_monitor, "SystemMonitor"):
                    system_monitor.SystemMonitor.stats = self._original_funcs["SystemMonitor.stats"]
            if "MemoryMonitor.stats" in self._original_funcs and memory_monitor is not None:
                if hasattr(memory_monitor, "MemoryMonitor"):
                    memory_monitor.MemoryMonitor.stats = self._original_funcs["MemoryMonitor.stats"]

        self._original_funcs.clear()

    def record_epoch(self, epoch: int, agent_step: int, epoch_time: float) -> None:
        """Record epoch timing."""
        self.epoch_times.append(
            {
                "epoch": epoch,
                "agent_step": agent_step,
                "epoch_time_s": epoch_time,
            }
        )
        self.total_agent_steps = agent_step

    def get_summary(self) -> dict[str, Any]:
        """Get profiling summary."""
        total_runtime = time.perf_counter() - self.start_time if self.start_time else 0.0

        # Calculate logging overhead percentage
        logging_components = [
            "wandb.run.log",
            "log_training_progress",
            "log_rich_progress",
            "build_wandb_payload",
        ]
        stats_components = [
            "accumulate_rollout_stats",
            "process_training_stats",
            "compute_timing_stats",
        ]
        monitoring_components = [
            "SystemMonitor.stats",
            "MemoryMonitor.stats",
        ]

        logging_time_ms = sum(self.stats.get(c, TimingStats(c)).total_time_ms for c in logging_components)
        stats_time_ms = sum(self.stats.get(c, TimingStats(c)).total_time_ms for c in stats_components)
        monitoring_time_ms = sum(self.stats.get(c, TimingStats(c)).total_time_ms for c in monitoring_components)

        total_overhead_ms = logging_time_ms + stats_time_ms + monitoring_time_ms
        total_runtime_ms = total_runtime * 1000

        overhead_pct = (total_overhead_ms / total_runtime_ms * 100) if total_runtime_ms > 0 else 0.0

        sps = self.total_agent_steps / total_runtime if total_runtime > 0 else 0.0

        return {
            "summary": {
                "total_runtime_s": round(total_runtime, 2),
                "total_agent_steps": self.total_agent_steps,
                "steps_per_second": round(sps, 1),
                "total_epochs": len(self.epoch_times),
                "total_overhead_ms": round(total_overhead_ms, 2),
                "overhead_pct_of_runtime": round(overhead_pct, 3),
            },
            "overhead_breakdown": {
                "logging_time_ms": round(logging_time_ms, 2),
                "stats_time_ms": round(stats_time_ms, 2),
                "monitoring_time_ms": round(monitoring_time_ms, 2),
            },
            "component_details": {name: stats.to_dict() for name, stats in sorted(self.stats.items())},
            "epoch_times": self.epoch_times[-10:],  # Last 10 epochs
        }

    def print_summary(self) -> None:
        """Print profiling summary to console."""
        summary = self.get_summary()

        print("\n" + "=" * 70)
        print("LOGGING AND METRICS OVERHEAD PROFILE")
        print("=" * 70)

        s = summary["summary"]
        print(f"\nRuntime: {s['total_runtime_s']:.1f}s")
        print(f"Steps:   {s['total_agent_steps']:,}")
        print(f"SPS:     {s['steps_per_second']:,.0f}")
        print(f"Epochs:  {s['total_epochs']}")

        overhead_ms = s["total_overhead_ms"]
        overhead_pct = s["overhead_pct_of_runtime"]
        print(f"\nTotal Logging Overhead: {overhead_ms:.1f}ms ({overhead_pct:.2f}% of runtime)")

        breakdown = summary["overhead_breakdown"]
        print("\nOverhead Breakdown:")
        print(f"  Logging (wandb, console):  {breakdown['logging_time_ms']:.1f}ms")
        print(f"  Stats computation:          {breakdown['stats_time_ms']:.1f}ms")
        print(f"  System monitoring:          {breakdown['monitoring_time_ms']:.1f}ms")

        print("\nComponent Details:")
        print("-" * 70)
        print(f"{'Component':<35} {'Calls':>8} {'Total(ms)':>12} {'Avg(ms)':>10}")
        print("-" * 70)

        for name, details in sorted(summary["component_details"].items()):
            calls = details["call_count"]
            total_ms = details["total_time_ms"]
            avg_ms = details["avg_time_ms"]
            print(f"{name:<35} {calls:>8} {total_ms:>12.2f} {avg_ms:>10.3f}")

        print("=" * 70)


# Global profiler instance
_profiler: LoggingProfiler | None = None


def get_profiler() -> LoggingProfiler:
    """Get the global profiler instance."""
    global _profiler
    if _profiler is None:
        _profiler = LoggingProfiler()
    return _profiler


def run_profiled_training(
    epochs: int = 5,
    output_file: str | None = None,
    disable_wandb: bool = False,
) -> dict[str, Any]:
    """Run training with profiling enabled.

    Args:
        epochs: Number of epochs to train
        output_file: Optional file to write results to
        disable_wandb: If True, disable wandb logging for baseline comparison

    Returns:
        Profiling summary dictionary
    """
    profiler = get_profiler()
    profiler.reset()
    profiler.install_all_patches()

    if not METTA_AVAILABLE or init_logging is None or cogsguard is None:
        logger.error("metta/cogsguard not available, cannot run profiled training")
        return {}

    try:
        # Initialize logging
        init_logging()

        # Configure a minimal training run
        os.environ["WANDB_MODE"] = "disabled" if disable_wandb else "online"

        # Use cogsguard recipe for testing
        tool = cogsguard.train()
        tool.trainer.total_timesteps = epochs * tool.trainer.batch_size * 4  # ~epochs worth

        # Run training
        profiler.start_time = time.perf_counter()
        tool.invoke({})

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
    finally:
        profiler.restore_all()

    summary = profiler.get_summary()

    if output_file:
        with open(output_file, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nResults written to {output_file}")

    profiler.print_summary()
    return summary


def main():
    parser = argparse.ArgumentParser(description="Profile logging and metrics overhead")
    parser.add_argument("--epochs", type=int, default=5, help="Number of epochs to train")
    parser.add_argument("--output", type=str, help="Output file for results (JSON)")
    parser.add_argument("--disable-wandb", action="store_true", help="Disable wandb for baseline comparison")

    args = parser.parse_args()

    summary = run_profiled_training(
        epochs=args.epochs,
        output_file=args.output,
        disable_wandb=args.disable_wandb,
    )
    if not summary:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
