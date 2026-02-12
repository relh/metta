#!/usr/bin/env python
"""Profile observation encoding pipeline from raw env output to model input tensors.

This script profiles the complete observation encoding pipeline:
1. Raw observation extraction from MettagGrid (C++ timing via step_timing)
2. Tensor conversion: numpy→torch tensor overhead
3. ObsTokenPadStrip: padding stripping and feature remapping
4. ObsAttrValNorm: value normalization
5. ObsAttrEmbedFourier / ObsAttrCoordEmbed: tokenization
6. ObsLatentAttn / ObsPerceiverLatent: attention encoding

Usage:
    uv run python tests/perf/profile_observation_encoding.py
    uv run python tests/perf/profile_observation_encoding.py --num-steps 5000 --batch-size 32
    uv run python tests/perf/profile_observation_encoding.py --torch-profile  # For detailed torch profiler output

Environment Variables:
    METTAGRID_PROFILING=1  - Enable C++ step timing breakdown
"""

import argparse
import os
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
from tensordict import TensorDict

from metta.agent.components.obs_enc import ObsLatentAttnConfig, ObsPerceiverLatentConfig
from metta.agent.components.obs_shim import ObsShimTokensConfig
from metta.agent.components.obs_tokenizers import ObsAttrEmbedFourierConfig
from mettagrid.envs.mettagrid_puffer_env import MettaGridPufferEnv
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Simulator
from recipes.experiment import cogsguard


@dataclass
class TimingResult:
    """Timing result for a single component."""

    name: str
    total_us: float
    mean_us: float
    pct_of_total: float


@dataclass
class ProfilingResults:
    """Complete profiling results."""

    num_steps: int
    batch_size: int
    num_agents: int
    total_wall_time_s: float
    agent_sps: int
    components: list[TimingResult]
    cpp_obs_time_us: Optional[float] = None


def profile_observation_encoding(
    num_steps: int = 2000,
    batch_size: int = 8,
    warmup_steps: int = 200,
    use_torch_profiler: bool = False,
    device: str = "cuda" if torch.cuda.is_available() else "cpu",
) -> ProfilingResults:
    """Profile the observation encoding pipeline."""
    os.environ["METTAGRID_PROFILING"] = "1"

    # Create environment
    config = cogsguard.make_env(num_agents=batch_size, layout="machina_1")
    simulator = Simulator()
    env = MettaGridPufferEnv(simulator, config)
    env.reset()

    num_agents = env.num_agents
    num_actions = env.single_action_space.n

    # Get policy environment interface for component initialization
    policy_env_info = PolicyEnvInterface.from_mg_cfg(config)

    # Create observation encoding components
    torch_device = torch.device(device)

    # 1. ObsShimTokens (pad strip + normalization)
    obs_shim_config = ObsShimTokensConfig(
        in_key="env_obs",
        out_key="obs_shim",
        ignore_inventory_power_tokens=False,
    )
    obs_shim = obs_shim_config.make_component(policy_env_info).to(torch_device)
    obs_shim.initialize_to_environment(policy_env_info, torch_device)

    # 2. ObsAttrEmbedFourier (tokenization)
    tokenizer_config = ObsAttrEmbedFourierConfig(
        in_key="obs_shim",
        out_key="obs_tokenized",
        attr_embed_dim=12,
        num_freqs=6,
    )
    tokenizer = tokenizer_config.make_component().to(torch_device)

    # 3. ObsLatentAttn (attention encoding)
    # feat_dim = attr_embed_dim + (4 * num_freqs) + 1 = 12 + 24 + 1 = 37
    latent_attn_config = ObsLatentAttnConfig(
        in_key="obs_tokenized",
        out_key="obs_encoded",
        feat_dim=37,
        out_dim=128,
        num_query_tokens=10,
        num_heads=4,
        num_layers=2,
        use_cls_token=True,
    )
    latent_attn = latent_attn_config.make_component().to(torch_device)

    # 4. Alternative: ObsPerceiverLatent
    perceiver_config = ObsPerceiverLatentConfig(
        in_key="obs_tokenized",
        out_key="obs_perceiver",
        feat_dim=37,
        latent_dim=64,
        num_latents=16,
        num_heads=4,
        num_layers=2,
    )
    perceiver = perceiver_config.make_component().to(torch_device)

    # Pre-generate random actions
    rng = np.random.RandomState(42)
    total_steps = warmup_steps + num_steps
    actions = rng.randint(0, num_actions, size=(total_steps, num_agents))

    c_sim = env.current_simulation._c_sim

    # Timing accumulators
    timings = {
        "env_step": [],
        "cpp_obs": [],
        "numpy_to_tensor": [],
        "obs_shim": [],
        "tokenizer": [],
        "latent_attn": [],
        "perceiver": [],
    }

    # Warmup
    print(f"Warming up for {warmup_steps} steps...")
    for i in range(warmup_steps):
        env.step(actions[i])

    # Profiled run
    print(f"Profiling {num_steps} steps on {device}...")

    if use_torch_profiler:
        activities = [torch.profiler.ProfilerActivity.CPU]
        if torch.cuda.is_available():
            activities.append(torch.profiler.ProfilerActivity.CUDA)

        with torch.profiler.profile(
            activities=activities,
            record_shapes=True,
            profile_memory=True,
            with_stack=True,
        ) as prof:
            _run_profiled_steps(
                env,
                actions,
                warmup_steps,
                total_steps,
                c_sim,
                obs_shim,
                tokenizer,
                latent_attn,
                perceiver,
                timings,
                torch_device,
            )

        # Print torch profiler results
        print("\n" + "=" * 60)
        print("Torch Profiler Results (sorted by CUDA time)")
        print("=" * 60)
        if torch.cuda.is_available():
            print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=20))
        else:
            print(prof.key_averages().table(sort_by="cpu_time_total", row_limit=20))
    else:
        wall_start = time.perf_counter()
        _run_profiled_steps(
            env,
            actions,
            warmup_steps,
            total_steps,
            c_sim,
            obs_shim,
            tokenizer,
            latent_attn,
            perceiver,
            timings,
            torch_device,
        )
        total_wall_time = time.perf_counter() - wall_start

    # Compute results
    if not use_torch_profiler:
        total_wall_time_s = total_wall_time
    else:
        total_wall_time_s = sum(timings["env_step"]) / 1e6

    agent_sps = int(num_steps * num_agents / total_wall_time_s) if total_wall_time_s > 0 else 0

    # Compute timing breakdown
    components = []
    total_pipeline_us = sum(sum(timings[k]) for k in ["obs_shim", "tokenizer", "latent_attn"])

    for name, times in timings.items():
        if not times:
            continue
        total_us = sum(times)
        mean_us = total_us / len(times) if times else 0
        pct = (total_us / total_pipeline_us * 100) if total_pipeline_us > 0 else 0
        components.append(TimingResult(name=name, total_us=total_us, mean_us=mean_us, pct_of_total=pct))

    cpp_obs_time = np.mean(timings["cpp_obs"]) if timings["cpp_obs"] else None

    return ProfilingResults(
        num_steps=num_steps,
        batch_size=batch_size,
        num_agents=num_agents,
        total_wall_time_s=total_wall_time_s,
        agent_sps=agent_sps,
        components=components,
        cpp_obs_time_us=cpp_obs_time,
    )


def _run_profiled_steps(
    env,
    actions,
    warmup_steps,
    total_steps,
    c_sim,
    obs_shim,
    tokenizer,
    latent_attn,
    perceiver,
    timings,
    device,
):
    """Run the profiled steps."""
    for i in range(warmup_steps, total_steps):
        # 1. Environment step (includes C++ observation generation)
        t0 = time.perf_counter_ns()
        obs, reward, done, truncated, info = env.step(actions[i])
        t1 = time.perf_counter_ns()
        timings["env_step"].append((t1 - t0) / 1000)

        # Get C++ observation timing
        cpp_obs_ns = c_sim.step_timing.observations_ns
        timings["cpp_obs"].append(cpp_obs_ns / 1000)

        # 2. Convert numpy observation to tensor
        t2 = time.perf_counter_ns()
        obs_tensor = torch.from_numpy(obs).to(device)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t3 = time.perf_counter_ns()
        timings["numpy_to_tensor"].append((t3 - t2) / 1000)

        # Create TensorDict for pipeline
        td = TensorDict({"env_obs": obs_tensor}, batch_size=[obs_tensor.shape[0]])

        # 3. ObsShimTokens (pad strip + normalization)
        t4 = time.perf_counter_ns()
        with torch.no_grad():
            td = obs_shim(td)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t5 = time.perf_counter_ns()
        timings["obs_shim"].append((t5 - t4) / 1000)

        # 4. Tokenization
        t6 = time.perf_counter_ns()
        with torch.no_grad():
            td = tokenizer(td)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t7 = time.perf_counter_ns()
        timings["tokenizer"].append((t7 - t6) / 1000)

        # 5. Latent attention encoding
        t8 = time.perf_counter_ns()
        with torch.no_grad():
            td = latent_attn(td)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t9 = time.perf_counter_ns()
        timings["latent_attn"].append((t9 - t8) / 1000)

        # 6. Perceiver (alternative path, just for comparison)
        # Reset tokenized output for perceiver
        td_perceiver = TensorDict({"obs_tokenized": td["obs_tokenized"].clone()}, batch_size=[obs_tensor.shape[0]])
        t10 = time.perf_counter_ns()
        with torch.no_grad():
            td_perceiver = perceiver(td_perceiver)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t11 = time.perf_counter_ns()
        timings["perceiver"].append((t11 - t10) / 1000)


def print_results(results: ProfilingResults):
    """Print profiling results."""
    print("\n" + "=" * 70)
    print("OBSERVATION ENCODING PIPELINE PROFILE")
    print("=" * 70)
    print(f"  Steps: {results.num_steps:,}")
    print(f"  Batch size: {results.batch_size}")
    print(f"  Num agents: {results.num_agents}")
    print(f"  Wall time: {results.total_wall_time_s:.2f}s")
    print(f"  Agent SPS: {results.agent_sps:,}")
    if results.cpp_obs_time_us:
        print(f"  C++ obs time: {results.cpp_obs_time_us:.2f} us/step")

    # Pipeline components only
    pipeline_components = ["obs_shim", "tokenizer", "latent_attn"]
    pipeline_total_us = sum(c.total_us for c in results.components if c.name in pipeline_components)

    print(f"\n  {'Component':<20} {'Mean (us)':>12} {'% of pipeline':>14}")
    print(f"  {'-' * 48}")

    for comp in results.components:
        if comp.name in pipeline_components:
            pct = (comp.total_us / pipeline_total_us * 100) if pipeline_total_us > 0 else 0
            print(f"  {comp.name:<20} {comp.mean_us:>12.2f} {pct:>13.1f}%")

    print(f"  {'-' * 48}")
    print(f"  {'Pipeline total':<20} {pipeline_total_us / results.num_steps:>12.2f}")

    # Full timing breakdown (including env step)
    print(f"\n  {'Full breakdown':<20} {'Mean (us)':>12} {'Note':<20}")
    print(f"  {'-' * 54}")
    for comp in results.components:
        note = ""
        if comp.name == "cpp_obs":
            note = "(C++ observation encoding)"
        elif comp.name == "env_step":
            note = "(full env.step())"
        elif comp.name == "perceiver":
            note = "(alternative to latent_attn)"
        print(f"  {comp.name:<20} {comp.mean_us:>12.2f} {note:<20}")


def main():
    parser = argparse.ArgumentParser(description="Profile observation encoding pipeline")
    parser.add_argument("--num-steps", type=int, default=2000, help="Number of steps to profile")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size (num agents)")
    parser.add_argument("--warmup-steps", type=int, default=200, help="Warmup steps")
    parser.add_argument("--torch-profile", action="store_true", help="Use torch profiler")
    parser.add_argument(
        "--device",
        type=str,
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Device to use",
    )
    args = parser.parse_args()

    results = profile_observation_encoding(
        num_steps=args.num_steps,
        batch_size=args.batch_size,
        warmup_steps=args.warmup_steps,
        use_torch_profiler=args.torch_profile,
        device=args.device,
    )

    print_results(results)

    # Summary for documentation
    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)

    pipeline_components = ["obs_shim", "tokenizer", "latent_attn"]
    pipeline_total_us = sum(c.total_us for c in results.components if c.name in pipeline_components)
    pipeline_mean_us = pipeline_total_us / results.num_steps if results.num_steps > 0 else 0

    cpp_obs = next((c for c in results.components if c.name == "cpp_obs"), None)
    latent_attn = next((c for c in results.components if c.name == "latent_attn"), None)

    if cpp_obs and latent_attn:
        print(f"  - C++ observation encoding: {cpp_obs.mean_us:.2f} us/step")
        print(f"  - Python observation pipeline: {pipeline_mean_us:.2f} us/step")
        print(f"  - Latent attention dominates pipeline: {latent_attn.mean_us:.2f} us/step")
        print(f"  - Ratio Python/C++: {pipeline_mean_us / cpp_obs.mean_us:.1f}x")


if __name__ == "__main__":
    main()
