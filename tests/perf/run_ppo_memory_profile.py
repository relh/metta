#!/usr/bin/env python3
"""Run a minimal PPO training loop with detailed memory profiling.

This runs the actual cogsguard training with memory instrumentation at each phase.
"""

from __future__ import annotations

import argparse
import gc
from dataclasses import dataclass
from pathlib import Path

import torch

from metta.agent.policies.default import DefaultPolicyConfig
from metta.cogworks.curriculum import env_curriculum
from metta.rl.checkpoint_manager import CheckpointManager
from metta.rl.policy_assets import PolicyAssetConfig, PolicyAssetRegistry
from metta.rl.system_config import SystemConfig
from metta.rl.trainer import Trainer
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import (
    Checkpointer,
    CheckpointerConfig,
    DistributedHelper,
    TrainingEnvironmentConfig,
    VectorizedTrainingEnvironment,
)
from metta.rl.training.trajectory_isolation import default_trajectory_isolation_config
from recipes.experiment import cogsguard


@dataclass
class PhaseMemory:
    """Memory stats for a training phase."""

    phase: str
    allocated_mb: float
    reserved_mb: float
    peak_allocated_mb: float
    delta_mb: float = 0.0


def get_cuda_memory(device: torch.device) -> tuple[float, float, float]:
    """Get current CUDA memory stats in MB."""
    if device.type != "cuda":
        return 0.0, 0.0, 0.0
    torch.cuda.synchronize(device)
    allocated = torch.cuda.memory_allocated(device) / 1024**2
    reserved = torch.cuda.memory_reserved(device) / 1024**2
    peak = torch.cuda.max_memory_allocated(device) / 1024**2
    return allocated, reserved, peak


def profile_training_epoch(
    num_agents: int = 8,
    batch_size: int = 4096,
    bptt_horizon: int = 16,
    minibatch_size: int = 1024,
    max_steps: int = 500,
    device: str = "cuda",
) -> list[PhaseMemory]:
    """Profile memory through one training epoch."""
    torch_device = torch.device(device)
    results: list[PhaseMemory] = []

    def snapshot(phase: str, prev_alloc: float = 0.0) -> float:
        alloc, res, peak = get_cuda_memory(torch_device)
        results.append(
            PhaseMemory(
                phase=phase,
                allocated_mb=alloc,
                reserved_mb=res,
                peak_allocated_mb=peak,
                delta_mb=alloc - prev_alloc,
            )
        )
        return alloc

    # Reset peak stats
    gc.collect()
    if torch_device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(torch_device)
        torch.cuda.empty_cache()

    prev = snapshot("initial", 0)

    # Create environment config
    env_cfg = cogsguard.make_env(num_agents=num_agents, max_steps=max_steps)
    curriculum = env_curriculum(env_cfg)

    prev = snapshot("curriculum_created", prev)

    # Create trainer config
    trainer_cfg = TrainerConfig(
        total_timesteps=batch_size * 3,  # Run 3 epochs worth
        batch_size=batch_size,
        minibatch_size=minibatch_size,
        bptt_horizon=bptt_horizon,
        update_epochs=1,
    )

    training_env_cfg = TrainingEnvironmentConfig(
        curriculum=curriculum,
        num_workers=1,
        async_factor=1,
        forward_pass_minibatch_target_size=128,
        vectorization="serial",
        seed=42,
    )

    system_cfg = SystemConfig(
        device=device,
        vectorization="serial",
        data_dir=Path("/tmp/metta_perf_profile"),
        seed=42,
        local_only=True,
    )

    prev = snapshot("configs_created", prev)

    # Create distributed helper
    distributed = DistributedHelper(system_cfg)

    # Create training environment
    training_env = VectorizedTrainingEnvironment(training_env_cfg, supervisor_policy_spec=None)

    prev = snapshot("training_env_created", prev)

    # Create policy
    architecture = DefaultPolicyConfig()

    # Create and load policy using Checkpointer
    checkpoint_manager = CheckpointManager(run="perf_profile", system_cfg=system_cfg)
    checkpointer = Checkpointer(
        config=CheckpointerConfig(),
        checkpoint_manager=checkpoint_manager,
        distributed_helper=distributed,
        policy_architecture=architecture,
        policy_name="learner0",
    )
    policy = checkpointer.load_or_create_policy(training_env.policy_env_info, policy_uri=None)

    prev = snapshot("policy_created", prev)

    # Create policy assets registry
    policy_assets = PolicyAssetRegistry(
        configs={"learner0": PolicyAssetConfig(architecture=architecture, run="perf_profile")},
        policies={"learner0": policy},
    )

    prev = snapshot("policy_registry_created", prev)

    # Create trajectory isolation config
    trajectory_isolation = default_trajectory_isolation_config()

    prev = snapshot("trajectory_isolation_created", prev)

    # Create trainer
    trainer = Trainer(
        cfg=trainer_cfg,
        env=training_env,
        policy_assets=policy_assets,
        losses_cfg=trainer_cfg.losses,
        trajectory_isolation=trajectory_isolation,
        device=torch_device,
        distributed_helper=distributed,
        run_name="perf_profile",
    )

    prev = snapshot("trainer_created", prev)

    # Analyze experience buffer
    exp_buffer = trainer._experience.buffer
    buffer_bytes = 0
    for key in exp_buffer.keys(include_nested=True, leaves_only=True):
        t = exp_buffer[key]
        if isinstance(t, torch.Tensor):
            buffer_bytes += t.numel() * t.element_size()

    print(f"\nExperience buffer size: {buffer_bytes / 1024**2:.2f} MB")
    print(f"  Segments: {trainer._experience.segments}")
    print(f"  BPTT horizon: {trainer._experience.bptt_horizon}")
    print(f"  Total agents: {trainer._experience.total_agents}")
    print(f"  Buffer shape: {exp_buffer.batch_size}")

    # Profile rollout phase
    if torch_device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(torch_device)

    print("\nRunning rollout phase...")
    # ScheduleFree optimizers must be in eval mode during rollout (normally handled in Trainer._run_epoch).
    for optimizer in trainer._iter_schedulefree_optimizers():
        optimizer.eval()
    trainer.core_loop.on_epoch_start(trainer._context)
    trainer.core_loop.rollout_phase(training_env, trainer._context)

    prev = snapshot("rollout_complete", prev)
    rollout_peak = 0.0
    if torch_device.type == "cuda":
        rollout_peak = torch.cuda.max_memory_allocated(torch_device) / 1024**2
        print(f"Rollout peak memory: {rollout_peak:.2f} MB")
    else:
        print("Rollout peak memory: N/A (CUDA-only metric)")

    # Profile training phase
    if torch_device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(torch_device)

    print("\nRunning training phase...")
    # ScheduleFree optimizers must be in train mode during training (normally handled in Trainer._run_epoch).
    for optimizer in trainer._iter_schedulefree_optimizers():
        optimizer.train()
    losses_stats, epochs_trained = trainer.core_loop.training_phase(
        context=trainer._context,
        update_epochs=1,
        max_grad_norm=0.5,
    )

    prev = snapshot("training_complete", prev)
    training_peak = 0.0
    if torch_device.type == "cuda":
        training_peak = torch.cuda.max_memory_allocated(torch_device) / 1024**2
        print(f"Training peak memory: {training_peak:.2f} MB")
    else:
        print("Training peak memory: N/A (CUDA-only metric)")

    # Get final stats
    snapshot("final", prev)

    # Print results
    print("\n" + "=" * 80)
    print("Memory Profile Results")
    print("=" * 80)
    print(f"{'Phase':<30} | {'Allocated':>12} | {'Reserved':>12} | {'Delta':>12}")
    print("-" * 80)
    for r in results:
        print(f"{r.phase:<30} | {r.allocated_mb:>10.2f}MB | {r.reserved_mb:>10.2f}MB | {r.delta_mb:>+10.2f}MB")

    print("\n" + "=" * 80)
    print("Key Findings")
    print("=" * 80)

    # Find key phases
    phase_map = {r.phase: r for r in results}

    if "trainer_created" in phase_map and "initial" in phase_map:
        setup_cost = phase_map["trainer_created"].allocated_mb - phase_map["initial"].allocated_mb
        print(f"Total setup cost: {setup_cost:.2f} MB")

    if "rollout_complete" in phase_map and "trainer_created" in phase_map:
        rollout_delta = phase_map["rollout_complete"].allocated_mb - phase_map["trainer_created"].allocated_mb
        print(f"Rollout memory delta: {rollout_delta:+.2f} MB")
        if torch_device.type == "cuda":
            print(f"Rollout peak memory: {rollout_peak:.2f} MB")
        else:
            print("Rollout peak memory: N/A (CUDA-only metric)")

    if "training_complete" in phase_map and "rollout_complete" in phase_map:
        training_delta = phase_map["training_complete"].allocated_mb - phase_map["rollout_complete"].allocated_mb
        print(f"Training memory delta: {training_delta:+.2f} MB")
        if torch_device.type == "cuda":
            print(f"Training peak memory: {training_peak:.2f} MB")
        else:
            print("Training peak memory: N/A (CUDA-only metric)")

    # Calculate steady state
    steady_state = phase_map["final"].allocated_mb
    overall_peak = max(r.peak_allocated_mb for r in results)
    print(f"\nSteady state memory: {steady_state:.2f} MB")
    print(f"Overall peak memory: {overall_peak:.2f} MB")
    print(f"Peak to steady-state ratio: {overall_peak / steady_state:.2f}x" if steady_state > 0 else "N/A")

    # Experience buffer analysis
    print(f"\nExperience buffer: {buffer_bytes / 1024**2:.2f} MB")
    print("  Pre-allocated: Yes")
    print(f"  Shape: {exp_buffer.batch_size}")

    # Cleanup
    training_env.close()

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-agents", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--bptt-horizon", type=int, default=16)
    parser.add_argument("--minibatch-size", type=int, default=1024)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        print("CUDA not available, falling back to CPU")
        args.device = "cpu"

    print("Configuration:")
    print(f"  Device: {args.device}")
    print(f"  Num agents: {args.num_agents}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  BPTT horizon: {args.bptt_horizon}")
    print(f"  Minibatch size: {args.minibatch_size}")
    print(f"  Max steps: {args.max_steps}")

    profile_training_epoch(
        num_agents=args.num_agents,
        batch_size=args.batch_size,
        bptt_horizon=args.bptt_horizon,
        minibatch_size=args.minibatch_size,
        max_steps=args.max_steps,
        device=args.device,
    )


if __name__ == "__main__":
    main()
