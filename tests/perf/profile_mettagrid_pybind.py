#!/usr/bin/env python3
"""MettagGrid/pybind performance profiling script.

Measures:
1. Pybind boundary overhead (Python wrapper vs C++ step time)
2. Per-phase step breakdown (requires METTAGRID_PROFILING=1)
3. Batch efficiency (N single steps vs vectorized operations)
4. GIL release behavior during step()

Usage:
    METTAGRID_PROFILING=1 uv run python tests/perf/profile_mettagrid_pybind.py --agents 8 --steps 10000
"""

import argparse
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from mettagrid.config.mettagrid_config import (
    ActionsConfig,
    GameConfig,
    MettaGridConfig,
    MoveActionConfig,
    NoopActionConfig,
    ObsConfig,
    WallConfig,
)
from mettagrid.envs.mettagrid_puffer_env import MettaGridPufferEnv
from mettagrid.map_builder.random_map import RandomMapBuilder
from mettagrid.simulator import Simulator


@dataclass
class ProfilingResults:
    """Container for profiling measurement results."""

    # Configuration
    num_agents: int = 0
    map_size: int = 0
    num_steps: int = 0
    warmup_steps: int = 0

    # SPS Metrics
    env_sps: float = 0.0
    agent_sps: float = 0.0

    # Pybind overhead
    python_step_time_us: float = 0.0
    cpp_step_time_us: float = 0.0
    pybind_overhead_us: float = 0.0
    pybind_overhead_pct: float = 0.0

    # Phase breakdown (microseconds)
    phase_times_us: dict = field(default_factory=dict)
    phase_percentages: dict = field(default_factory=dict)

    # Batch efficiency
    single_step_time_us: float = 0.0
    batch_step_time_us: float = 0.0
    batch_efficiency_ratio: float = 0.0

    # GIL info
    gil_released: bool = False

    def to_dict(self) -> dict:
        return {
            "config": {
                "num_agents": self.num_agents,
                "map_size": self.map_size,
                "num_steps": self.num_steps,
                "warmup_steps": self.warmup_steps,
            },
            "sps": {
                "env_sps": self.env_sps,
                "agent_sps": self.agent_sps,
            },
            "pybind_overhead": {
                "python_step_time_us": self.python_step_time_us,
                "cpp_step_time_us": self.cpp_step_time_us,
                "pybind_overhead_us": self.pybind_overhead_us,
                "pybind_overhead_pct": self.pybind_overhead_pct,
            },
            "phase_breakdown_us": self.phase_times_us,
            "phase_breakdown_pct": self.phase_percentages,
            "batch_efficiency": {
                "single_step_time_us": self.single_step_time_us,
                "batch_efficiency_ratio": self.batch_efficiency_ratio,
            },
        }


def create_env(num_agents: int = 8, map_size: int = 40, seed: int = 42):
    """Create a mettagrid environment for profiling."""
    num_walls = int(map_size * map_size * 0.04)

    cfg = MettaGridConfig(
        game=GameConfig(
            num_agents=num_agents,
            max_steps=0,  # infinite
            obs=ObsConfig(width=11, height=11, num_tokens=200),
            actions=ActionsConfig(
                noop=NoopActionConfig(enabled=True),
                move=MoveActionConfig(
                    enabled=True,
                    allowed_directions=[
                        "north",
                        "south",
                        "east",
                        "west",
                        "northeast",
                        "northwest",
                        "southeast",
                        "southwest",
                    ],
                ),
            ),
            objects={
                "wall": WallConfig(render_symbol="X"),
            },
            map_builder=RandomMapBuilder.Config(
                width=map_size,
                height=map_size,
                agents=num_agents,
                objects={"wall": num_walls},
                border_width=1,
                border_object="wall",
                seed=seed,
            ),
        )
    )

    simulator = Simulator()
    env = MettaGridPufferEnv(simulator, cfg)
    env.reset()
    return env


def measure_pybind_overhead(
    env,
    num_steps: int,
    warmup_steps: int,
) -> tuple[float, float, dict]:
    """Measure Python wrapper overhead vs C++ step time.

    Returns:
        (python_step_time_us, cpp_step_time_us, phase_times_us)
    """
    num_agents = env.num_agents
    num_actions = env.single_action_space.n
    total_steps = warmup_steps + num_steps

    # Pre-generate actions
    rng = np.random.RandomState(42)
    actions = rng.randint(0, num_actions, size=(total_steps, num_agents), dtype=np.int32)

    c_sim = env.current_simulation._c_sim
    profiling_enabled = os.environ.get("METTAGRID_PROFILING") == "1"

    # Warmup
    for i in range(warmup_steps):
        env.step(actions[i])

    # Measure Python-level step time
    python_times = []
    phase_totals = {}

    if profiling_enabled:
        phases = [
            "reset",
            "events",
            "actions",
            "on_tick",
            "aoe",
            "observations",
            "rewards",
            "truncation",
        ]
        for phase in phases:
            phase_totals[phase] = 0.0
        phase_totals["total"] = 0.0

    for i in range(warmup_steps, total_steps):
        # Measure Python step time
        start = time.perf_counter_ns()
        env.step(actions[i])
        end = time.perf_counter_ns()
        python_times.append(end - start)

        if profiling_enabled:
            timing = c_sim.step_timing
            for phase in phases:
                phase_totals[phase] += getattr(timing, f"{phase}_ns")
            phase_totals["total"] += timing.total_ns

    python_step_us = np.mean(python_times) / 1000.0
    cpp_step_us = (phase_totals["total"] / num_steps) / 1000.0 if profiling_enabled else 0.0

    phase_times_us = {phase: (ns / num_steps) / 1000.0 for phase, ns in phase_totals.items()}

    return python_step_us, cpp_step_us, phase_times_us


def measure_batch_efficiency(env, batch_sizes: list[int] = None) -> dict:
    """Measure overhead of calling step() N times vs theoretical batch.

    Since MettagGrid doesn't have true batching, we compare
    single env step time across different scenarios.
    """
    if batch_sizes is None:
        batch_sizes = [1, 10, 100]

    num_actions = env.single_action_space.n
    num_agents = env.num_agents

    results = {}
    for batch in batch_sizes:
        rng = np.random.RandomState(42)
        actions = rng.randint(0, num_actions, size=(batch, num_agents), dtype=np.int32)

        # Warmup
        for i in range(min(batch, 100)):
            env.step(actions[i % batch])

        # Measure
        start = time.perf_counter_ns()
        for i in range(batch):
            env.step(actions[i])
        end = time.perf_counter_ns()

        results[batch] = (end - start) / batch / 1000.0  # us per step

    return results


def check_gil_release() -> bool:
    """Check if MettaGrid step() releases the GIL.

    We can infer this from documentation or testing with threading.
    """
    # Based on code review: MettaGrid uses pybind11 with py::gil_scoped_release
    # in long-running operations. Let's check if the binding has it.
    try:
        cfg = MettaGridConfig(
            game=GameConfig(
                num_agents=4,
                max_steps=0,
                actions=ActionsConfig(
                    noop=NoopActionConfig(enabled=True),
                    move=MoveActionConfig(enabled=True),
                ),
                map_builder=RandomMapBuilder.Config(
                    width=20,
                    height=20,
                    agents=4,
                    seed=42,
                ),
            )
        )
        simulator = Simulator()
        env = MettaGridPufferEnv(simulator, cfg)
        env.reset()

        # Run step in a thread and see if main thread can make progress
        counter = [0]
        done = [False]

        def background_work():
            while not done[0]:
                counter[0] += 1
                time.sleep(0.0001)

        t = threading.Thread(target=background_work)
        t.start()

        initial_count = counter[0]
        for _ in range(100):
            env.step(np.zeros(4, dtype=np.int32))

        done[0] = True
        t.join()

        # If counter advanced, the GIL was released during step()
        env.reset()
        return counter[0] > initial_count + 10

    except Exception:
        return False


def run_profiling(
    num_agents: int = 8,
    map_size: int = 40,
    num_steps: int = 10000,
    warmup_steps: int = 1000,
    output_file: Optional[str] = None,
) -> ProfilingResults:
    """Run comprehensive profiling and return results."""

    results = ProfilingResults(
        num_agents=num_agents,
        map_size=map_size,
        num_steps=num_steps,
        warmup_steps=warmup_steps,
    )

    print(f"Creating environment: {num_agents} agents on {map_size}x{map_size} map")
    env = create_env(num_agents=num_agents, map_size=map_size)

    # 1. Measure pybind overhead
    print(f"Measuring pybind overhead ({num_steps} steps)...")
    python_us, cpp_us, phase_times = measure_pybind_overhead(env, num_steps, warmup_steps)

    results.python_step_time_us = python_us
    results.cpp_step_time_us = cpp_us
    results.pybind_overhead_us = python_us - cpp_us
    results.pybind_overhead_pct = ((python_us - cpp_us) / python_us * 100) if python_us > 0 else 0
    results.phase_times_us = phase_times

    # Calculate phase percentages
    total = phase_times["total"] if phase_times else 1.0
    results.phase_percentages = {
        phase: (t / total * 100) if total > 0 else 0 for phase, t in phase_times.items() if phase != "total"
    }

    # 2. Calculate SPS
    results.env_sps = 1_000_000 / python_us if python_us > 0 else 0
    results.agent_sps = results.env_sps * num_agents

    # 3. Measure batch efficiency
    print("Measuring batch efficiency...")
    batch_results = measure_batch_efficiency(env)
    results.single_step_time_us = batch_results[1]
    if 100 in batch_results and 1 in batch_results:
        results.batch_efficiency_ratio = batch_results[1] / batch_results[100]

    # 4. Check GIL release
    print("Checking GIL release behavior...")
    results.gil_released = check_gil_release()

    # Print summary
    print("\n" + "=" * 60)
    print("PROFILING RESULTS SUMMARY")
    print("=" * 60)

    print("\nConfiguration:")
    print(f"  Agents: {num_agents}")
    print(f"  Map size: {map_size}x{map_size}")
    print(f"  Steps: {num_steps}")

    print("\nPerformance Metrics:")
    print(f"  Env SPS: {results.env_sps:,.0f}")
    print(f"  Agent SPS: {results.agent_sps:,.0f}")

    print("\nPybind Boundary Overhead:")
    print(f"  Python step time: {python_us:.2f} us")
    print(f"  C++ step time: {cpp_us:.2f} us")
    print(f"  Pybind overhead: {results.pybind_overhead_us:.2f} us ({results.pybind_overhead_pct:.1f}%)")

    if phase_times:
        print("\nStep Phase Breakdown:")
        print(f"  {'Phase':<20} {'Time (us)':>12} {'% of step':>12}")
        print(f"  {'-' * 46}")
        sorted_phases = sorted([(p, t) for p, t in results.phase_percentages.items()], key=lambda x: -x[1])
        for phase, pct in sorted_phases:
            time_us = phase_times[phase]
            print(f"  {phase:<20} {time_us:>12.2f} {pct:>11.1f}%")
        print(f"  {'-' * 46}")
        print(f"  {'total (C++)':<20} {cpp_us:>12.2f} {'100.0%':>12}")

    print(f"\nGIL Release: {'Yes' if results.gil_released else 'No/Unknown'}")

    if output_file:
        with open(output_file, "w") as f:
            json.dump(results.to_dict(), f, indent=2)
        print(f"\nResults saved to: {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Profile MettagGrid/pybind performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--agents", type=int, default=8, help="Number of agents")
    parser.add_argument("--map-size", type=int, default=40, help="Map width/height")
    parser.add_argument("--steps", type=int, default=10000, help="Number of steps to measure")
    parser.add_argument("--warmup", type=int, default=1000, help="Warmup steps")
    parser.add_argument("--output", type=str, help="Save results to JSON file")
    args = parser.parse_args()

    if os.environ.get("METTAGRID_PROFILING") != "1":
        print("WARNING: METTAGRID_PROFILING=1 not set. Phase breakdown will be unavailable.")
        print("Run with: METTAGRID_PROFILING=1 python profile_mettagrid_pybind.py ...")
        print()

    run_profiling(
        num_agents=args.agents,
        map_size=args.map_size,
        num_steps=args.steps,
        warmup_steps=args.warmup,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
