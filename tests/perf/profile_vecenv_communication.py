#!/usr/bin/env python
"""Profile vectorized environment communication overhead.

This script profiles the IPC, serialization, and synchronization overhead
in PufferLib's vectorized environment communication with MettaGrid.

Usage:
    # Basic profile (Serial backend, 4 envs)
    uv run python tests/perf/profile_vecenv_communication.py

    # With multiprocessing (4 workers, 16 envs)
    uv run python tests/perf/profile_vecenv_communication.py \
        --vectorization multiprocessing --num-workers 4 --num-envs 16

    # Extended profile duration
    uv run python tests/perf/profile_vecenv_communication.py --duration 30

    # Output JSON report
    uv run python tests/perf/profile_vecenv_communication.py --output profile_results.json
"""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import psutil

# Ensure metta package is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pufferlib
import pufferlib.vector
from metta.cogworks.curriculum import Curriculum
from metta.rl.vecenv import make_vecenv
from recipes.experiment import cogsguard


@dataclass
class TimingStats:
    """Statistics for a timing measurement."""

    name: str
    count: int = 0
    total_ms: float = 0.0
    samples: list[float] = field(default_factory=list)

    @property
    def mean_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0

    @property
    def std_ms(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.samples) if self.samples else 0.0

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.samples) if self.samples else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.samples:
            return 0.0
        idx = int(len(self.samples) * 0.95)
        return sorted(self.samples)[min(idx, len(self.samples) - 1)]

    @property
    def p99_ms(self) -> float:
        if not self.samples:
            return 0.0
        idx = int(len(self.samples) * 0.99)
        return sorted(self.samples)[min(idx, len(self.samples) - 1)]

    def record(self, duration_s: float) -> None:
        duration_ms = duration_s * 1000
        self.count += 1
        self.total_ms += duration_ms
        self.samples.append(duration_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "total_ms": round(self.total_ms, 4),
            "mean_ms": round(self.mean_ms, 4),
            "std_ms": round(self.std_ms, 4),
            "min_ms": round(self.min_ms, 4),
            "max_ms": round(self.max_ms, 4),
            "p50_ms": round(self.p50_ms, 4),
            "p95_ms": round(self.p95_ms, 4),
            "p99_ms": round(self.p99_ms, 4),
        }


@dataclass
class ProfileResults:
    """Complete profiling results."""

    # Configuration
    vectorization: str = ""
    num_envs: int = 0
    num_workers: int = 0
    num_agents_per_env: int = 0
    batch_size: int = 0
    duration_s: float = 0.0

    # SPS metrics
    total_steps: int = 0
    total_agent_steps: int = 0
    sps: float = 0.0  # Steps per second (environment steps)
    agent_sps: float = 0.0  # Agent steps per second

    # Timing breakdowns
    recv_timing: TimingStats = field(default_factory=lambda: TimingStats("recv"))
    send_timing: TimingStats = field(default_factory=lambda: TimingStats("send"))
    step_timing: TimingStats = field(default_factory=lambda: TimingStats("step"))

    # Memory metrics
    shared_memory_bytes: int = 0
    observation_size_bytes: int = 0
    action_size_bytes: int = 0

    # Process metrics
    cpu_cores: int = 0
    initial_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "configuration": {
                "vectorization": self.vectorization,
                "num_envs": self.num_envs,
                "num_workers": self.num_workers,
                "num_agents_per_env": self.num_agents_per_env,
                "batch_size": self.batch_size,
                "duration_s": round(self.duration_s, 2),
            },
            "performance": {
                "total_steps": self.total_steps,
                "total_agent_steps": self.total_agent_steps,
                "sps": round(self.sps, 2),
                "agent_sps": round(self.agent_sps, 2),
            },
            "timing": {
                "recv": self.recv_timing.to_dict(),
                "send": self.send_timing.to_dict(),
                "step": self.step_timing.to_dict(),
            },
            "memory": {
                "shared_memory_bytes": self.shared_memory_bytes,
                "observation_size_bytes": self.observation_size_bytes,
                "action_size_bytes": self.action_size_bytes,
            },
            "system": {
                "cpu_cores": self.cpu_cores,
                "initial_memory_mb": round(self.initial_memory_mb, 2),
                "peak_memory_mb": round(self.peak_memory_mb, 2),
            },
        }


def calculate_shared_memory_size(vecenv: pufferlib.vector.Multiprocessing) -> int:
    """Calculate total shared memory allocation for multiprocessing vecenv."""
    if not hasattr(vecenv, "shm"):
        return 0

    total = 0
    for _name, arr in vecenv.shm.items():
        try:
            total += ctypes.sizeof(arr)
        except Exception:
            # Some sharedctypes wrappers expose the underlying ctypes object as `_obj`.
            raw = getattr(arr, "_obj", None)
            if raw is not None:
                try:
                    total += ctypes.sizeof(raw)
                except Exception:
                    pass
    return total


def profile_vecenv(
    vectorization: str = "serial",
    num_envs: int = 4,
    num_workers: int = 4,
    num_agents: int = 8,
    duration_s: float = 10.0,
    warmup_steps: int = 100,
) -> ProfileResults:
    """Profile vectorized environment communication overhead.

    Args:
        vectorization: "serial" or "multiprocessing"
        num_envs: Number of environments
        num_workers: Number of worker processes (for multiprocessing)
        num_agents: Number of agents per environment
        duration_s: Duration of profiling run in seconds
        warmup_steps: Number of warmup steps before profiling

    Returns:
        ProfileResults with timing and memory metrics
    """
    if vectorization == "multiprocessing" and num_workers < 2:
        raise ValueError(
            "vectorization='multiprocessing' requires num_workers >= 2. "
            "PufferLib coerces num_workers=1 to the serial backend."
        )
    results = ProfileResults(
        vectorization=vectorization,
        num_envs=num_envs,
        num_workers=num_workers,
        num_agents_per_env=num_agents,
        cpu_cores=psutil.cpu_count(logical=False) or 1,
    )

    # Record initial memory
    process = psutil.Process()
    results.initial_memory_mb = process.memory_info().rss / 1024 / 1024
    peak_memory = results.initial_memory_mb

    # Create curriculum and environment
    print(f"Creating cogsguard curriculum with {num_agents} agents...")
    env_cfg = cogsguard.make_env(num_agents=num_agents, max_steps=1000)
    curriculum_cfg = cogsguard.make_curriculum(env=env_cfg)
    curriculum = Curriculum(curriculum_cfg)

    print(f"Creating vecenv: {vectorization}, {num_envs} envs, {num_workers} workers...")
    batch_size = num_envs if vectorization == "serial" else num_envs
    vecenv = make_vecenv(
        curriculum=curriculum,
        vectorization=vectorization,
        num_envs=num_envs,
        batch_size=batch_size,
        num_workers=num_workers,
    )

    results.batch_size = getattr(vecenv, "agents_per_batch", num_envs * num_agents)

    # Calculate memory metrics
    obs_space = vecenv.single_observation_space
    atn_space = vecenv.single_action_space
    results.observation_size_bytes = int(np.prod(obs_space.shape)) * np.dtype(obs_space.dtype).itemsize
    results.action_size_bytes = int(np.prod(atn_space.shape)) * np.dtype(np.int32).itemsize

    if vectorization == "multiprocessing" and hasattr(vecenv, "shm"):
        results.shared_memory_bytes = calculate_shared_memory_size(vecenv)

    # Reset environment
    print("Resetting environment...")
    vecenv.async_reset(seed=42)
    _ = vecenv.recv()

    # Warmup phase
    print(f"Warming up ({warmup_steps} steps)...")
    for _ in range(warmup_steps):
        actions = vecenv.action_space.sample()
        vecenv.send(actions)
        vecenv.recv()

    peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)

    # Profile phase
    print(f"Profiling for {duration_s} seconds...")
    start_time = time.perf_counter()
    step_count = 0
    agent_step_count = 0

    while time.perf_counter() - start_time < duration_s:
        # Time the full step cycle
        step_start = time.perf_counter()

        # Time send
        actions = vecenv.action_space.sample()
        send_start = time.perf_counter()
        vecenv.send(actions)
        results.send_timing.record(time.perf_counter() - send_start)

        # Time recv
        recv_start = time.perf_counter()
        o, r, d, t, ta, info, env_id, mask = vecenv.recv()
        results.recv_timing.record(time.perf_counter() - recv_start)

        # Record full step time
        results.step_timing.record(time.perf_counter() - step_start)

        step_count += 1
        agent_step_count += len(r)

        # Periodic memory check
        if step_count % 100 == 0:
            peak_memory = max(peak_memory, process.memory_info().rss / 1024 / 1024)

    results.duration_s = time.perf_counter() - start_time
    results.total_steps = step_count
    results.total_agent_steps = agent_step_count
    results.sps = step_count / results.duration_s
    results.agent_sps = agent_step_count / results.duration_s
    results.peak_memory_mb = peak_memory

    # Cleanup
    vecenv.close()

    return results


def print_results(results: ProfileResults) -> None:
    """Print profiling results in a readable format."""
    print("\n" + "=" * 70)
    print("VECTORIZED ENVIRONMENT COMMUNICATION PROFILE")
    print("=" * 70)

    print("\n## Configuration")
    print(f"  Vectorization:     {results.vectorization}")
    print(f"  Num Envs:          {results.num_envs}")
    print(f"  Num Workers:       {results.num_workers}")
    print(f"  Agents per Env:    {results.num_agents_per_env}")
    print(f"  Batch Size:        {results.batch_size}")
    print(f"  Duration:          {results.duration_s:.2f}s")

    print("\n## Performance")
    print(f"  Total Steps:       {results.total_steps:,}")
    print(f"  Total Agent Steps: {results.total_agent_steps:,}")
    print(f"  SPS:               {results.sps:,.2f} steps/s")
    print(f"  Agent SPS:         {results.agent_sps:,.2f} agent-steps/s")

    print("\n## Timing Breakdown (per step)")
    total_time = results.step_timing.mean_ms
    recv_pct = (results.recv_timing.mean_ms / total_time * 100) if total_time > 0 else 0
    send_pct = (results.send_timing.mean_ms / total_time * 100) if total_time > 0 else 0

    print(f"  Step (total):      {results.step_timing.mean_ms:.4f} ms (p95: {results.step_timing.p95_ms:.4f} ms)")
    print(f"  ├── recv:          {results.recv_timing.mean_ms:.4f} ms ({recv_pct:.1f}%)")
    print(f"  │   └── p95:       {results.recv_timing.p95_ms:.4f} ms")
    print(f"  └── send:          {results.send_timing.mean_ms:.4f} ms ({send_pct:.1f}%)")
    print(f"      └── p95:       {results.send_timing.p95_ms:.4f} ms")

    print("\n## Memory")
    print(f"  Shared Memory:     {results.shared_memory_bytes / 1024 / 1024:.2f} MB")
    print(f"  Obs Size (each):   {results.observation_size_bytes:,} bytes")
    print(f"  Action Size:       {results.action_size_bytes:,} bytes")
    print(f"  Initial RSS:       {results.initial_memory_mb:.2f} MB")
    print(f"  Peak RSS:          {results.peak_memory_mb:.2f} MB")

    print("\n## System")
    print(f"  CPU Cores:         {results.cpu_cores}")

    # Analysis
    print("\n## Analysis")

    # IPC overhead estimate
    if results.vectorization == "multiprocessing":
        # For multiprocessing, recv waits for worker processes
        print(f"  IPC overhead:      ~{recv_pct:.1f}% of step time in recv (semaphore polling + pipe reads)")
    else:
        print("  No IPC (serial):   Single-process, no inter-process communication")

    # Memory efficiency
    obs_bandwidth_mbps = (results.observation_size_bytes * results.agent_sps) / 1024 / 1024
    print(f"  Obs bandwidth:     {obs_bandwidth_mbps:.2f} MB/s")

    # Synchronization analysis
    mean_ms = results.step_timing.mean_ms
    step_variance = results.step_timing.std_ms / mean_ms * 100 if mean_ms > 0 else 0
    print(f"  Step time variance: {step_variance:.1f}% (high = sync bottleneck)")

    print("\n" + "=" * 70)


def compare_backends(
    num_envs: int = 8,
    num_workers: int = 4,
    num_agents: int = 8,
    duration_s: float = 10.0,
) -> dict[str, ProfileResults]:
    """Compare serial vs multiprocessing backends."""
    results = {}

    print("\n### Serial Backend ###")
    results["serial"] = profile_vecenv(
        vectorization="serial",
        num_envs=num_envs,
        num_workers=1,
        num_agents=num_agents,
        duration_s=duration_s,
    )
    print_results(results["serial"])

    print("\n### Multiprocessing Backend ###")
    results["multiprocessing"] = profile_vecenv(
        vectorization="multiprocessing",
        num_envs=num_envs,
        num_workers=num_workers,
        num_agents=num_agents,
        duration_s=duration_s,
    )
    print_results(results["multiprocessing"])

    # Comparison
    print("\n" + "=" * 70)
    print("COMPARISON: Serial vs Multiprocessing")
    print("=" * 70)

    serial_sps = results["serial"].agent_sps
    mp_sps = results["multiprocessing"].agent_sps
    speedup = mp_sps / serial_sps if serial_sps > 0 else 0

    print(f"  Serial Agent SPS:        {serial_sps:,.2f}")
    print(f"  Multiprocessing SPS:     {mp_sps:,.2f}")
    print(f"  Speedup:                 {speedup:.2f}x")
    print(f"  Workers:                 {num_workers}")
    print(f"  Parallel Efficiency:     {speedup / num_workers * 100:.1f}%")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile vectorized environment communication")
    parser.add_argument(
        "--vectorization",
        choices=["serial", "multiprocessing", "compare"],
        default="serial",
        help="Vectorization backend to profile",
    )
    parser.add_argument("--num-envs", type=int, default=4, help="Number of environments")
    parser.add_argument("--num-workers", type=int, default=4, help="Number of worker processes")
    parser.add_argument("--num-agents", type=int, default=8, help="Agents per environment")
    parser.add_argument("--duration", type=float, default=10.0, help="Profile duration in seconds")
    parser.add_argument("--warmup", type=int, default=100, help="Warmup steps")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file")
    args = parser.parse_args()

    if args.vectorization == "compare":
        results = compare_backends(
            num_envs=args.num_envs,
            num_workers=args.num_workers,
            num_agents=args.num_agents,
            duration_s=args.duration,
        )
        if args.output:
            output_data = {k: v.to_dict() for k, v in results.items()}
            with open(args.output, "w") as f:
                json.dump(output_data, f, indent=2)
            print(f"\nResults saved to {args.output}")
    else:
        results = profile_vecenv(
            vectorization=args.vectorization,
            num_envs=args.num_envs,
            num_workers=args.num_workers,
            num_agents=args.num_agents,
            duration_s=args.duration,
            warmup_steps=args.warmup,
        )
        print_results(results)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(results.to_dict(), f, indent=2)
            print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
