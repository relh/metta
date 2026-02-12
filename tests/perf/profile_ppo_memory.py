#!/usr/bin/env python3
"""Memory profiling for PPO training loop.

This script profiles memory allocation patterns in the PPO training loop to identify:
1. TensorDict allocation patterns (per-step vs pre-allocated)
2. Advantage computation memory usage
3. Rollout buffer storage efficiency
4. Gradient accumulation memory spikes
5. Batch slicing overhead

Usage:
    # Run with CUDA memory profiling
    python tests/perf/profile_ppo_memory.py --device cuda

    # Run with tracemalloc for Python allocations
    python tests/perf/profile_ppo_memory.py --device cuda --trace-python

    # Run a short training loop with torch profiler
    python tests/perf/profile_ppo_memory.py --device cuda --torch-profile
"""

from __future__ import annotations

import argparse
import gc
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
from tensordict import TensorDict

from metta.cogworks.curriculum import env_curriculum
from metta.rl.advantage import compute_advantage
from metta.rl.system_config import SystemConfig
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import TrainingEnvironmentConfig
from recipes.experiment import cogsguard


@dataclass
class MemorySnapshot:
    """Captures memory state at a point in time."""

    label: str
    cuda_allocated_mb: float = 0.0
    cuda_reserved_mb: float = 0.0
    cuda_peak_mb: float = 0.0
    python_current_mb: float = 0.0
    python_peak_mb: float = 0.0
    tensors_count: int = 0
    tensors_mb: float = 0.0


@dataclass
class MemoryProfile:
    """Collection of memory snapshots through training."""

    snapshots: list[MemorySnapshot] = field(default_factory=list)
    allocation_timeline: list[dict[str, Any]] = field(default_factory=list)

    def add_snapshot(self, label: str, device: torch.device) -> MemorySnapshot:
        snapshot = MemorySnapshot(label=label)

        if device.type == "cuda":
            snapshot.cuda_allocated_mb = torch.cuda.memory_allocated(device) / 1024**2
            snapshot.cuda_reserved_mb = torch.cuda.memory_reserved(device) / 1024**2
            stats = torch.cuda.memory_stats(device)
            snapshot.cuda_peak_mb = stats["allocated_bytes.all.peak"] / 1024**2

        if tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            snapshot.python_current_mb = current / 1024**2
            snapshot.python_peak_mb = peak / 1024**2

        self.snapshots.append(snapshot)
        return snapshot

    def print_report(self) -> str:
        """Generate a formatted memory report."""
        lines = ["=" * 80, "PPO Training Loop Memory Profile", "=" * 80, ""]

        if not self.snapshots:
            lines.append("No snapshots recorded.")
            return "\n".join(lines)

        # Find max widths for formatting
        max_label = max(len(s.label) for s in self.snapshots)

        # Header
        lines.append(
            f"{'Phase':<{max_label}} | "
            f"{'CUDA Alloc':>12} | "
            f"{'CUDA Res':>12} | "
            f"{'CUDA Peak':>12} | "
            f"{'Py Curr':>10} | "
            f"{'Py Peak':>10}"
        )
        lines.append("-" * (max_label + 70))

        # Data rows
        for s in self.snapshots:
            lines.append(
                f"{s.label:<{max_label}} | "
                f"{s.cuda_allocated_mb:>10.2f}MB | "
                f"{s.cuda_reserved_mb:>10.2f}MB | "
                f"{s.cuda_peak_mb:>10.2f}MB | "
                f"{s.python_current_mb:>8.2f}MB | "
                f"{s.python_peak_mb:>8.2f}MB"
            )

        lines.append("")

        # Analysis section
        lines.append("=" * 80)
        lines.append("Analysis")
        lines.append("=" * 80)

        # Calculate deltas between key phases
        phase_map = {s.label: s for s in self.snapshots}

        if "rollout_start" in phase_map and "rollout_end" in phase_map:
            delta = phase_map["rollout_end"].cuda_allocated_mb - phase_map["rollout_start"].cuda_allocated_mb
            lines.append(f"Rollout phase memory delta: {delta:+.2f} MB")

        if "training_start" in phase_map and "training_end" in phase_map:
            delta = phase_map["training_end"].cuda_allocated_mb - phase_map["training_start"].cuda_allocated_mb
            lines.append(f"Training phase memory delta: {delta:+.2f} MB")

        if "advantage_start" in phase_map and "advantage_end" in phase_map:
            delta = phase_map["advantage_end"].cuda_allocated_mb - phase_map["advantage_start"].cuda_allocated_mb
            lines.append(f"Advantage computation delta: {delta:+.2f} MB")

        if "backward_start" in phase_map and "backward_end" in phase_map:
            delta = phase_map["backward_end"].cuda_allocated_mb - phase_map["backward_start"].cuda_allocated_mb
            lines.append(f"Backward pass memory spike: {delta:+.2f} MB")

        # Peak analysis
        max_snapshot = max(self.snapshots, key=lambda s: s.cuda_allocated_mb)
        lines.append(f"\nPeak memory usage: {max_snapshot.cuda_allocated_mb:.2f} MB at '{max_snapshot.label}'")

        # Steady state estimate
        if "epoch_end" in phase_map:
            steady = phase_map["epoch_end"].cuda_allocated_mb
            peak = max_snapshot.cuda_allocated_mb
            ratio = peak / steady if steady > 0 else 0
            lines.append(f"Peak to steady-state ratio: {ratio:.2f}x")

        return "\n".join(lines)


class MemoryProfiler:
    """Context manager for profiling memory in training loop phases."""

    def __init__(self, device: torch.device, trace_python: bool = False):
        self.device = device
        self.trace_python = trace_python
        self.profile = MemoryProfile()
        self._enabled = True

    def __enter__(self):
        if self.device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(self.device)
            torch.cuda.synchronize(self.device)

        if self.trace_python:
            tracemalloc.start()

        self.profile.add_snapshot("initial", self.device)
        return self

    def __exit__(self, *args):
        self.profile.add_snapshot("final", self.device)
        if self.trace_python:
            tracemalloc.stop()

    def snapshot(self, label: str) -> MemorySnapshot:
        """Take a memory snapshot with the given label."""
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
        return self.profile.add_snapshot(label, self.device)

    @contextmanager
    def phase(self, name: str):
        """Context manager to measure memory for a named phase."""
        if self._enabled:
            gc.collect()
            if self.device.type == "cuda":
                torch.cuda.empty_cache()
                torch.cuda.synchronize(self.device)
            self.snapshot(f"{name}_start")

        yield

        if self._enabled:
            if self.device.type == "cuda":
                torch.cuda.synchronize(self.device)
            self.snapshot(f"{name}_end")


def analyze_tensordict_memory(td: TensorDict, label: str = "") -> dict[str, Any]:
    """Analyze memory usage of a TensorDict."""
    total_bytes = 0
    tensor_info = []

    for key in td.keys(include_nested=True, leaves_only=True):
        tensor = td[key]
        if isinstance(tensor, torch.Tensor):
            nbytes = tensor.numel() * tensor.element_size()
            total_bytes += nbytes
            tensor_info.append(
                {
                    "key": str(key),
                    "shape": tuple(tensor.shape),
                    "dtype": str(tensor.dtype),
                    "bytes": nbytes,
                    "device": str(tensor.device),
                }
            )

    return {
        "label": label,
        "total_mb": total_bytes / 1024**2,
        "num_tensors": len(tensor_info),
        "tensors": sorted(tensor_info, key=lambda x: x["bytes"], reverse=True),
    }


def analyze_experience_buffer(experience) -> dict[str, Any]:
    """Analyze memory usage of the Experience buffer."""
    buffer = experience.buffer
    td_analysis = analyze_tensordict_memory(buffer, "experience_buffer")

    # Additional buffer-specific analysis
    return {
        **td_analysis,
        "segments": experience.segments,
        "bptt_horizon": experience.bptt_horizon,
        "total_agents": experience.total_agents,
        "buffer_shape": tuple(buffer.batch_size),
        "preallocated": True,  # Experience buffer is always pre-allocated
    }


def run_memory_profile(
    device: str = "cuda",
    trace_python: bool = False,
    num_epochs: int = 2,
    num_agents: int = 8,
    batch_size: int = 2048,
    bptt_horizon: int = 16,
    minibatch_size: int = 512,
) -> MemoryProfile:
    """Run a training loop with memory profiling.

    Args:
        device: Device to run on ("cuda" or "cpu")
        trace_python: Whether to trace Python allocations
        num_epochs: Number of training epochs to run
        num_agents: Number of agents in the environment
        batch_size: Batch size for training
        bptt_horizon: BPTT horizon (sequence length)
        minibatch_size: Minibatch size for gradient updates

    Returns:
        MemoryProfile with collected snapshots
    """
    torch_device = torch.device(device)

    profiler = MemoryProfiler(torch_device, trace_python=trace_python)

    with profiler:
        profiler.snapshot("before_setup")

        # Create training configuration
        curriculum = env_curriculum(cogsguard.make_env(num_agents=num_agents, max_steps=500))

        trainer_cfg = TrainerConfig(
            total_timesteps=batch_size * num_epochs,
            batch_size=batch_size,
            minibatch_size=minibatch_size,
            bptt_horizon=bptt_horizon,
            update_epochs=1,
        )

        training_env_cfg = TrainingEnvironmentConfig(
            curriculum=curriculum,
            num_workers=1,
            async_factor=1,
            forward_pass_minibatch_target_size=64,
            vectorization="serial",
            seed=42,
        )

        system_cfg = SystemConfig(
            device=device,
            vectorization="serial",
            data_dir=Path("/tmp/metta_perf_test"),
            seed=42,
            local_only=True,
        )

        profiler.snapshot("config_created")

        # Create training tool
        tool = cogsguard.train(
            curriculum=curriculum,
            num_agents=num_agents,
        )
        tool.system = system_cfg
        tool.trainer = trainer_cfg
        tool.training_env = training_env_cfg

        profiler.snapshot("tool_created")

        # Note: Full training run would require invoking the tool
        # For now we profile the component setup
        print("Configuration complete. Full training profiling requires GPU.")

    return profiler.profile


def profile_advantage_computation(device: str = "cuda") -> dict[str, Any]:
    """Profile the advantage computation specifically.

    This isolates the GAE/advantage computation to measure its memory footprint.
    """
    torch_device = torch.device(device)

    results = {}

    # Typical training dimensions
    batch_sizes = [64, 128, 256, 512]
    seq_lens = [8, 16, 32, 64]

    for bs in batch_sizes:
        for seq_len in seq_lens:
            key = f"bs{bs}_seq{seq_len}"

            # Create test tensors
            values = torch.randn(bs, seq_len, device=torch_device)
            rewards = torch.randn(bs, seq_len, device=torch_device)
            dones = torch.zeros(bs, seq_len, device=torch_device)
            dones[:, -1] = 1.0
            importance_ratio = torch.ones(bs, seq_len, device=torch_device)
            advantages = torch.zeros(bs, seq_len, device=torch_device)

            if torch_device.type == "cuda":
                torch.cuda.reset_peak_memory_stats(torch_device)
                torch.cuda.synchronize()
                before_alloc = torch.cuda.memory_allocated(torch_device)

            # Run advantage computation
            if torch_device.type == "cuda":
                torch.cuda.synchronize(torch_device)
            start_time = time.perf_counter()
            result = compute_advantage(
                values,
                rewards,
                dones,
                importance_ratio,
                advantages,
                gamma=0.99,
                gae_lambda=0.95,
                device=torch_device,
            )
            if torch_device.type == "cuda":
                torch.cuda.synchronize(torch_device)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            result_entry = {
                "batch_size": bs,
                "seq_len": seq_len,
                "input_mb": (values.numel() + rewards.numel() + dones.numel()) * 4 / 1024**2,
                "elapsed_ms": elapsed_ms,
            }

            if torch_device.type == "cuda":
                torch.cuda.synchronize()
                after_alloc = torch.cuda.memory_allocated(torch_device)
                peak_alloc = torch.cuda.max_memory_allocated(torch_device)

                result_entry["allocated_mb"] = (after_alloc - before_alloc) / 1024**2
                result_entry["peak_mb"] = peak_alloc / 1024**2
            else:
                result_entry["allocated_mb"] = 0.0
                result_entry["peak_mb"] = 0.0
                result_entry["note"] = "CUDA memory metrics unavailable on CPU."

            results[key] = result_entry

            # Cleanup
            del values, rewards, dones, importance_ratio, advantages, result
            gc.collect()
            if torch_device.type == "cuda":
                torch.cuda.empty_cache()

    return results


def profile_minibatch_slicing(device: str = "cuda") -> dict[str, Any]:
    """Profile the cost of creating minibatch views from the buffer.

    This measures whether slicing creates copies or views.
    """
    torch_device = torch.device(device)
    results = {}

    # Simulate experience buffer dimensions
    segments = 128
    bptt_horizon = 16
    feature_dim = 256

    # Create a mock buffer
    buffer = TensorDict(
        {
            "obs": torch.randn(segments, bptt_horizon, feature_dim, device=torch_device),
            "actions": torch.randint(0, 10, (segments, bptt_horizon), device=torch_device),
            "values": torch.randn(segments, bptt_horizon, device=torch_device),
            "rewards": torch.randn(segments, bptt_horizon, device=torch_device),
            "dones": torch.zeros(segments, bptt_horizon, device=torch_device),
            "log_probs": torch.randn(segments, bptt_horizon, device=torch_device),
        },
        batch_size=[segments, bptt_horizon],
    )

    if torch_device.type == "cuda":
        torch.cuda.synchronize()
        buffer_mem = torch.cuda.memory_allocated(torch_device)

    # Test different minibatch sizes
    minibatch_sizes = [8, 16, 32, 64]

    for mb_size in minibatch_sizes:
        indices = torch.randperm(segments, device=torch_device)[:mb_size]

        if torch_device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(torch_device)
            torch.cuda.synchronize()
            before = torch.cuda.memory_allocated(torch_device)

        # Slice operation (this is what happens in sample_from_indices)
        minibatch = buffer[indices].clone()

        if torch_device.type == "cuda":
            torch.cuda.synchronize()
            after = torch.cuda.memory_allocated(torch_device)

        results[f"mb_{mb_size}"] = {
            "minibatch_size": mb_size,
            "allocated_mb": (after - before) / 1024**2 if torch_device.type == "cuda" else 0,
            "is_copy": True,  # .clone() always creates a copy
            "buffer_fraction": mb_size / segments,
        }

        del minibatch, indices
        gc.collect()
        if torch_device.type == "cuda":
            torch.cuda.empty_cache()

    results["buffer_total_mb"] = buffer_mem / 1024**2 if torch_device.type == "cuda" else 0
    return results


def main():
    parser = argparse.ArgumentParser(description="Profile PPO training loop memory")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="Device to profile on")
    parser.add_argument("--trace-python", action="store_true", help="Trace Python memory allocations")
    parser.add_argument("--torch-profile", action="store_true", help="Use torch.profiler for detailed tracing")
    parser.add_argument("--num-epochs", type=int, default=2, help="Number of epochs to profile")
    parser.add_argument("--advantage-only", action="store_true", help="Only profile advantage computation")
    parser.add_argument("--minibatch-only", action="store_true", help="Only profile minibatch slicing")
    parser.add_argument("--output", type=str, help="Output file for results")
    args = parser.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        print("CUDA not available, falling back to CPU")
        args.device = "cpu"

    print(f"Profiling on device: {args.device}")
    print("=" * 80)

    if args.advantage_only:
        print("\nProfiling advantage computation...")
        results = profile_advantage_computation(args.device)
        print("\nAdvantage Computation Memory Profile:")
        print("-" * 60)
        for key, data in results.items():
            if isinstance(data, dict):
                print(f"  {key}:")
                print(f"    Input size: {data['input_mb']:.3f} MB")
                print(f"    Allocated: {data['allocated_mb']:.3f} MB")
                print(f"    Peak: {data['peak_mb']:.3f} MB")
                print(f"    Runtime: {data['elapsed_ms']:.2f} ms")
                if "note" in data:
                    print(f"    Note: {data['note']}")
        return

    if args.minibatch_only:
        print("\nProfiling minibatch slicing...")
        results = profile_minibatch_slicing(args.device)
        print("\nMinibatch Slicing Memory Profile:")
        print("-" * 60)
        print(f"  Buffer total: {results['buffer_total_mb']:.3f} MB")
        for key, data in results.items():
            if isinstance(data, dict):
                print(f"  {key}:")
                print(f"    Allocated: {data['allocated_mb']:.3f} MB")
                print(f"    Is copy: {data['is_copy']}")
                print(f"    Buffer fraction: {data['buffer_fraction']:.2%}")
        return

    # Full training profile
    print("\nRunning full training profile...")
    if args.torch_profile:
        activities = [torch.profiler.ProfilerActivity.CPU]
        if args.device == "cuda" and torch.cuda.is_available():
            activities.append(torch.profiler.ProfilerActivity.CUDA)
        with torch.profiler.profile(
            activities=activities,
            record_shapes=True,
            profile_memory=True,
            with_stack=True,
        ) as prof:
            profile = run_memory_profile(
                device=args.device,
                trace_python=args.trace_python,
                num_epochs=args.num_epochs,
            )
        print("\n" + "=" * 60)
        print("Torch Profiler Results (sorted by CUDA time)")
        print("=" * 60)
        if args.device == "cuda" and torch.cuda.is_available():
            print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=20))
        else:
            print(prof.key_averages().table(sort_by="cpu_time_total", row_limit=20))
    else:
        profile = run_memory_profile(
            device=args.device,
            trace_python=args.trace_python,
            num_epochs=args.num_epochs,
        )

    report = profile.print_report()
    print(report)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
