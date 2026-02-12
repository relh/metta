#!/usr/bin/env -S uv run
"""Profile the policy network forward pass components for performance analysis.

This script profiles individual components of the ViT policy architecture used in cogsguard,
breaking down timing by component and layer type.

Usage:
    uv run tests/perf/profile_policy_forward.py
    uv run tests/perf/profile_policy_forward.py --batch-sizes 32 64 128 256
    uv run tests/perf/profile_policy_forward.py --sweep-mode
"""

import argparse
import logging
import statistics
import time
from typing import Callable

import torch
from tensordict import TensorDict

from metta.agent.components.obs_enc import ObsPerceiverLatent, ObsPerceiverLatentConfig
from metta.agent.components.obs_shim import ObsShimTokens, ObsShimTokensConfig
from metta.agent.components.obs_tokenizers import ObsAttrEmbedFourier, ObsAttrEmbedFourierConfig
from metta.agent.policies.vit import ViTDefaultConfig
from mettagrid.builder.envs import make_arena
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator.simulator import Simulator

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def create_policy_env_info(num_agents: int = 6) -> tuple[PolicyEnvInterface, Simulator]:
    """Create a PolicyEnvInterface from the arena environment."""
    cfg = make_arena(num_agents=num_agents)
    sim = Simulator().new_simulation(cfg, seed=0)
    policy_env_info = PolicyEnvInterface.from_mg_cfg(cfg)
    return policy_env_info, sim


def collect_observations(sim: Simulator, steps: int = 20) -> list[torch.Tensor]:
    """Collect real observations from the simulator."""
    obs_list: list[torch.Tensor] = []
    c_sim = sim._c_sim  # noqa: SLF001
    for _ in range(steps):
        obs_np = c_sim.observations().copy()  # [agents, M, 3] uint8
        obs_list.append(torch.from_numpy(obs_np))
        c_sim.actions()[:] = 0  # noop
        sim.step()
    return obs_list


def _time_run(fn: Callable[[], None], device: torch.device) -> float:
    """Time a single function execution with CUDA synchronization."""
    if device.type == "cuda":
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        fn()
        end.record()
        torch.cuda.synchronize(device=device)
        return start.elapsed_time(end)
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000.0


def benchmark_obs_encoding_pipeline(
    obs_list: list[torch.Tensor],
    policy_env_info: PolicyEnvInterface,
    device: torch.device,
    dtype: torch.dtype,
    config: ViTDefaultConfig,
    warmup: int = 5,
    iters: int = 50,
) -> dict[str, dict[str, float]]:
    """Benchmark the observation encoding pipeline components."""
    max_tokens = config.max_tokens
    attr_embed_dim = config._token_embed_dim
    num_freqs = config._fourier_freqs
    feat_dim = attr_embed_dim + (4 * num_freqs) + 1

    # Create components
    shim = ObsShimTokens(
        policy_env_info,
        ObsShimTokensConfig(
            in_key="env_obs",
            out_key="tokens",
            max_tokens=max_tokens,
            ignore_inventory_power_tokens=config.obs_shim_ignore_inventory_power_tokens,
        ),
    ).to(device)

    embed = ObsAttrEmbedFourier(
        ObsAttrEmbedFourierConfig(
            in_key="tokens",
            out_key="obs_attr_embed",
            attr_embed_dim=attr_embed_dim,
            num_freqs=num_freqs,
        )
    ).to(device)

    perceiver = ObsPerceiverLatent(
        ObsPerceiverLatentConfig(
            in_key="obs_attr_embed",
            out_key="enc",
            feat_dim=feat_dim,
            latent_dim=config.latent_dim,
            num_latents=config.core_num_latents,
            num_heads=config.core_num_heads,
            num_layers=2,
            mlp_ratio=4.0,
            use_mask=False,
            pool="mean",
        )
    ).to(device=device, dtype=dtype)

    results: dict[str, dict[str, float]] = {}

    # Benchmark each component
    with torch.inference_mode():
        obs_list_dev = [obs.to(device) for obs in obs_list]

        # Warmup
        logger.info("  Warming up...")
        for _ in range(warmup):
            for obs in obs_list_dev[:3]:
                td = TensorDict({"env_obs": obs}, batch_size=[obs.shape[0]])
                td = shim(td)
                td = embed(td)
                td["obs_attr_embed"] = td["obs_attr_embed"].to(dtype)
                perceiver(td)
        if device.type == "cuda":
            torch.cuda.synchronize(device=device)

        # Benchmark full pipeline
        logger.info("  Benchmarking full obs encoding pipeline...")
        times: list[float] = []
        for _ in range(iters):
            for obs in obs_list_dev:

                def _run_pipeline(obs=obs) -> None:
                    td = TensorDict({"env_obs": obs}, batch_size=[obs.shape[0]])
                    td = shim(td)
                    td = embed(td)
                    td["obs_attr_embed"] = td["obs_attr_embed"].to(dtype)
                    perceiver(td)

                times.append(_time_run(_run_pipeline, device))

        results["full_pipeline"] = {
            "mean_ms": statistics.mean(times),
            "median_ms": statistics.median(times),
            "std_ms": statistics.stdev(times) if len(times) > 1 else 0,
            "min_ms": min(times),
            "max_ms": max(times),
        }

        # Benchmark individual components
        for name, _component, _in_key, _out_key in [
            ("shim", shim, "env_obs", "tokens"),
            ("embed", embed, "tokens", "obs_attr_embed"),
            ("perceiver", perceiver, "obs_attr_embed", "enc"),
        ]:
            logger.info(f"  Benchmarking {name}...")
            times = []
            for _ in range(iters):
                for obs in obs_list_dev:
                    td = TensorDict({"env_obs": obs}, batch_size=[obs.shape[0]])
                    td = shim(td)
                    if name != "shim":
                        td = embed(td)
                        if name == "perceiver":
                            td["obs_attr_embed"] = td["obs_attr_embed"].to(dtype)

                    if name == "shim":

                        def _run(td=td) -> None:
                            shim(td.clone())

                    elif name == "embed":

                        def _run(td=td) -> None:
                            embed(td.clone())

                    else:

                        def _run(td=td) -> None:
                            perceiver(td.clone())

                    times.append(_time_run(_run, device))

            results[name] = {
                "mean_ms": statistics.mean(times),
                "median_ms": statistics.median(times),
                "std_ms": statistics.stdev(times) if len(times) > 1 else 0,
                "min_ms": min(times),
                "max_ms": max(times),
            }

    return results


def benchmark_batch_scaling(
    obs_list: list[torch.Tensor],
    policy_env_info: PolicyEnvInterface,
    batch_sizes: list[int],
    device: torch.device,
    dtype: torch.dtype,
    config: ViTDefaultConfig,
    iters: int = 20,
) -> dict[int, dict[str, float]]:
    """Benchmark how encoding time scales with batch size."""
    max_tokens = config.max_tokens
    attr_embed_dim = config._token_embed_dim
    num_freqs = config._fourier_freqs
    feat_dim = attr_embed_dim + (4 * num_freqs) + 1

    shim = ObsShimTokens(
        policy_env_info,
        ObsShimTokensConfig(
            in_key="env_obs",
            out_key="tokens",
            max_tokens=max_tokens,
        ),
    ).to(device)

    embed = ObsAttrEmbedFourier(
        ObsAttrEmbedFourierConfig(
            in_key="tokens",
            out_key="obs_attr_embed",
            attr_embed_dim=attr_embed_dim,
            num_freqs=num_freqs,
        )
    ).to(device)

    perceiver = ObsPerceiverLatent(
        ObsPerceiverLatentConfig(
            in_key="obs_attr_embed",
            out_key="enc",
            feat_dim=feat_dim,
            latent_dim=config.latent_dim,
            num_latents=config.core_num_latents,
            num_heads=config.core_num_heads,
            num_layers=2,
        )
    ).to(device=device, dtype=dtype)

    # Concatenate all observations
    all_obs = torch.cat(obs_list, dim=0).to(device)

    results = {}

    with torch.inference_mode():
        for batch_size in batch_sizes:
            # Prepare batch
            if batch_size > all_obs.shape[0]:
                # Repeat observations to fill batch
                repeat_factor = (batch_size // all_obs.shape[0]) + 1
                batch_obs = all_obs.repeat(repeat_factor, 1, 1)[:batch_size]
            else:
                batch_obs = all_obs[:batch_size]

            # Warmup
            for _ in range(3):
                td = TensorDict({"env_obs": batch_obs}, batch_size=[batch_size])
                td = shim(td)
                td = embed(td)
                td["obs_attr_embed"] = td["obs_attr_embed"].to(dtype)
                perceiver(td)
            if device.type == "cuda":
                torch.cuda.synchronize(device=device)

            # Benchmark
            times: list[float] = []
            for _ in range(iters):

                def _run(batch_obs=batch_obs, batch_size=batch_size) -> None:
                    td = TensorDict({"env_obs": batch_obs}, batch_size=[batch_size])
                    td = shim(td)
                    td = embed(td)
                    td["obs_attr_embed"] = td["obs_attr_embed"].to(dtype)
                    perceiver(td)

                times.append(_time_run(_run, device))

            mean_ms = statistics.mean(times)
            throughput = batch_size / (mean_ms / 1000) if mean_ms > 0 else 0

            results[batch_size] = {
                "mean_ms": mean_ms,
                "median_ms": statistics.median(times),
                "std_ms": statistics.stdev(times) if len(times) > 1 else 0,
                "throughput_samples_per_sec": throughput,
            }
            logger.info(f"  Batch {batch_size:4d}: {mean_ms:.3f}ms, {throughput:.0f} samples/sec")

    return results


def main():
    parser = argparse.ArgumentParser(description="Profile policy network forward pass components")
    parser.add_argument("--batch-sizes", nargs="+", type=int, default=[32, 64, 128, 256, 512])
    parser.add_argument("--num-agents", type=int, default=6)
    parser.add_argument("--sweep-mode", action="store_true", help="Use sweep_mode architecture params")
    parser.add_argument("--dtype", choices=["float16", "bfloat16", "float32"], default="float16")
    parser.add_argument("--iters", type=int, default=50, help="Benchmark iterations")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup iterations")
    args = parser.parse_args()

    dtype_map = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}
    dtype = dtype_map[args.dtype]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")
    if device.type == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name()}")
    logger.info(f"Dtype: {dtype}")

    # Create environment and collect observations
    policy_env_info, sim = create_policy_env_info(args.num_agents)

    if args.sweep_mode:
        config = ViTDefaultConfig(
            obs_shim_ignore_inventory_power_tokens=False,
            actor_hidden=384,
            critic_hidden=768,
            latent_dim=96,
            core_resnet_layers=1,
            core_num_heads=4,
            core_num_latents=16,
        )
        logger.info("Using sweep_mode architecture (1.17M params)")
    else:
        config = ViTDefaultConfig(obs_shim_ignore_inventory_power_tokens=False)
        logger.info("Using default architecture (2.8M params)")

    logger.info(f"Architecture: latent_dim={config.latent_dim}, core_num_latents={config.core_num_latents}")

    # Collect observations
    logger.info("\nCollecting observations from environment...")
    obs_list = collect_observations(sim, steps=20)
    logger.info(f"Collected {len(obs_list)} steps, obs shape: {obs_list[0].shape}")

    # Benchmark observation encoding pipeline
    logger.info("\n=== Observation Encoding Pipeline ===")
    component_results = benchmark_obs_encoding_pipeline(
        obs_list,
        policy_env_info,
        device,
        dtype,
        config,
        warmup=args.warmup,
        iters=args.iters,
    )

    logger.info("\nComponent Breakdown:")
    for name, stats in sorted(component_results.items(), key=lambda x: -x[1]["mean_ms"]):
        logger.info(
            f"  {name:20s}: mean={stats['mean_ms']:7.3f}ms, "
            f"median={stats['median_ms']:7.3f}ms, std={stats['std_ms']:6.3f}ms"
        )

    # Calculate percentages
    total_time = component_results["full_pipeline"]["mean_ms"]
    logger.info("\nPercentage of Full Pipeline:")
    for name in ["shim", "embed", "perceiver"]:
        if name in component_results:
            pct = component_results[name]["mean_ms"] / total_time * 100
            logger.info(f"  {name:20s}: {pct:5.1f}%")

    # Benchmark batch scaling
    logger.info("\n=== Batch Size Scaling ===")
    batch_results = benchmark_batch_scaling(
        obs_list,
        policy_env_info,
        args.batch_sizes,
        device,
        dtype,
        config,
        iters=args.iters // 2,
    )

    # Summary
    logger.info("\n=== Summary ===")
    logger.info(f"Full obs encoding pipeline: {component_results['full_pipeline']['mean_ms']:.3f}ms")
    if "perceiver" in component_results:
        logger.info(f"Perceiver cross-attention: {component_results['perceiver']['mean_ms']:.3f}ms")

    best_batch = max(batch_results.items(), key=lambda x: x[1]["throughput_samples_per_sec"])
    best_throughput = best_batch[1]["throughput_samples_per_sec"]
    logger.info(f"Best throughput at batch {best_batch[0]}: {best_throughput:.0f} samples/sec")

    return {
        "components": component_results,
        "batch_scaling": batch_results,
    }


if __name__ == "__main__":
    main()
