#!/usr/bin/env python
"""Profile the action processing pipeline for RL training.

This script measures:
1. Action sampling timing (sample_actions)
2. Action evaluation timing (evaluate_actions)
3. Log probability computation
4. Entropy calculation
5. GPU-CPU transfer overhead
6. ActorHead forward pass

Usage:
    uv run python tests/perf/profile_action_pipeline.py
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import torch
import torch.nn.functional as F

try:
    from torch.profiler import ProfilerActivity, profile, record_function

    TORCH_PROFILER_AVAILABLE = True
except ImportError:
    TORCH_PROFILER_AVAILABLE = False

# Import the actual functions we're profiling
from metta.agent.util.distribution_utils import evaluate_actions, sample_actions


@dataclass
class TimingResult:
    """Timing result for a single operation."""

    name: str
    mean_ms: float
    std_ms: float
    min_ms: float
    max_ms: float
    samples: int

    def __str__(self) -> str:
        return (
            f"{self.name}: {self.mean_ms:.4f}ms (std={self.std_ms:.4f}, min={self.min_ms:.4f}, max={self.max_ms:.4f})"
        )


def measure_operation(
    op_name: str,
    op_fn,
    warmup_iters: int = 10,
    measure_iters: int = 100,
    device: str = "cuda",
) -> TimingResult:
    """Measure execution time of an operation."""
    # Warmup
    for _ in range(warmup_iters):
        _ = op_fn()
        if device == "cuda":
            torch.cuda.synchronize()

    # Measure
    times_ms = []
    for _ in range(measure_iters):
        if device == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        _ = op_fn()
        if device == "cuda":
            torch.cuda.synchronize()
        end = time.perf_counter()
        times_ms.append((end - start) * 1000)

    times_tensor = torch.tensor(times_ms)
    return TimingResult(
        name=op_name,
        mean_ms=times_tensor.mean().item(),
        std_ms=times_tensor.std().item(),
        min_ms=times_tensor.min().item(),
        max_ms=times_tensor.max().item(),
        samples=len(times_ms),
    )


def profile_sample_actions(
    batch_sizes: list[int],
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile sample_actions for different batch sizes."""
    results = {}
    for batch_size in batch_sizes:
        logits = torch.randn(batch_size, num_actions, device=device)

        def op(logits=logits):
            return sample_actions(logits)

        result = measure_operation(
            f"sample_actions (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_evaluate_actions(
    batch_sizes: list[int],
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile evaluate_actions for different batch sizes."""
    results = {}
    for batch_size in batch_sizes:
        logits = torch.randn(batch_size, num_actions, device=device)
        actions = torch.randint(0, num_actions, (batch_size,), device=device)

        def op(logits=logits, actions=actions):
            return evaluate_actions(logits, actions)

        result = measure_operation(
            f"evaluate_actions (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_log_softmax(
    batch_sizes: list[int],
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile F.log_softmax for different batch sizes."""
    results = {}
    for batch_size in batch_sizes:
        logits = torch.randn(batch_size, num_actions, device=device)

        def op(logits=logits):
            return F.log_softmax(logits, dim=-1)

        result = measure_operation(
            f"log_softmax (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_multinomial_sampling(
    batch_sizes: list[int],
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile torch.multinomial for different batch sizes."""
    results = {}
    for batch_size in batch_sizes:
        probs = torch.softmax(torch.randn(batch_size, num_actions, device=device), dim=-1)

        def op(probs=probs):
            return torch.multinomial(probs, num_samples=1)

        result = measure_operation(
            f"multinomial (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_entropy_computation(
    batch_sizes: list[int],
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile entropy computation for different batch sizes."""
    results = {}
    for batch_size in batch_sizes:
        log_probs = F.log_softmax(torch.randn(batch_size, num_actions, device=device), dim=-1)
        probs = torch.exp(log_probs)

        def op(probs=probs, log_probs=log_probs):
            return -torch.sum(probs * log_probs, dim=-1)

        result = measure_operation(
            f"entropy (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_exp(
    batch_sizes: list[int],
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile torch.exp(log_probs) for different batch sizes."""
    results = {}
    for batch_size in batch_sizes:
        log_probs = F.log_softmax(torch.randn(batch_size, num_actions, device=device), dim=-1)

        def op(log_probs=log_probs):
            return torch.exp(log_probs)

        result = measure_operation(
            f"exp (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_action_logprob_indexing(
    batch_sizes: list[int],
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile log-prob extraction via gather used in sample_actions()."""
    results = {}
    for batch_size in batch_sizes:
        log_probs = F.log_softmax(torch.randn(batch_size, num_actions, device=device), dim=-1)
        actions = torch.randint(0, num_actions, (batch_size, 1), device=device)

        def op(log_probs=log_probs, actions=actions):
            return log_probs.gather(dim=-1, index=actions).squeeze(-1)

        result = measure_operation(
            f"log_prob indexing (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_gpu_cpu_transfer(
    batch_sizes: list[int],
    num_actions: int = 21,
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile GPU to CPU tensor transfer for different batch sizes."""
    results = {}
    for batch_size in batch_sizes:
        actions = torch.randint(0, num_actions, (batch_size,), device="cuda")

        def op(actions=actions):
            return actions.cpu()

        result = measure_operation(
            f"gpu_to_cpu (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device="cuda",
        )
        results[batch_size] = result
    return results


def profile_actor_head_forward(
    batch_sizes: list[int],
    hidden_dim: int = 512,
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile simple linear head (ActorHead equivalent) forward pass."""
    results = {}
    linear = torch.nn.Linear(hidden_dim, num_actions).to(device)
    linear.eval()

    for batch_size in batch_sizes:
        hidden = torch.randn(batch_size, hidden_dim, device=device)

        def op(linear=linear, hidden=hidden):
            with torch.no_grad():
                return linear(hidden)

        result = measure_operation(
            f"actor_head (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def profile_full_pipeline(
    batch_sizes: list[int],
    hidden_dim: int = 512,
    num_actions: int = 21,
    device: str = "cuda",
    warmup_iters: int = 10,
    measure_iters: int = 100,
) -> dict[int, TimingResult]:
    """Profile full action pipeline: linear -> sample_actions."""
    results = {}
    linear = torch.nn.Linear(hidden_dim, num_actions).to(device)
    linear.eval()

    for batch_size in batch_sizes:
        hidden = torch.randn(batch_size, hidden_dim, device=device)

        def op(linear=linear, hidden=hidden):
            with torch.no_grad():
                logits = linear(hidden)
                return sample_actions(logits)

        result = measure_operation(
            f"full_pipeline (B={batch_size})",
            op,
            warmup_iters=warmup_iters,
            measure_iters=measure_iters,
            device=device,
        )
        results[batch_size] = result
    return results


def run_torch_profiler(
    batch_size: int = 4096,
    hidden_dim: int = 512,
    num_actions: int = 21,
    device: str = "cuda",
) -> None:
    """Run torch profiler for detailed analysis."""
    if not TORCH_PROFILER_AVAILABLE:
        print("\n=== Torch Profiler Not Available ===")
        return

    linear = torch.nn.Linear(hidden_dim, num_actions).to(device)
    linear.eval()
    hidden = torch.randn(batch_size, hidden_dim, device=device)
    logits = torch.randn(batch_size, num_actions, device=device)
    actions = torch.randint(0, num_actions, (batch_size,), device=device)

    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA], record_shapes=True) as prof:
        for _ in range(10):
            with record_function("actor_head"):
                logits_out = linear(hidden)

            with record_function("sample_actions"):
                _, _, _, _ = sample_actions(logits_out)

            with record_function("evaluate_actions"):
                _, _, _ = evaluate_actions(logits, actions)

            with record_function("gpu_to_cpu_transfer"):
                _ = logits_out.cpu()

    print("\n=== Torch Profiler Results ===")
    print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=20))


def main() -> None:
    """Run all profiling tests and generate report."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"CUDA version: {torch.version.cuda}")

    # Batch sizes to test (matching training configurations)
    batch_sizes = [256, 512, 1024, 2048, 4096, 8192]
    num_actions = 21  # CogsGuard action space
    hidden_dim = 512  # Typical actor hidden dimension

    print("\n" + "=" * 70)
    print("ACTION PROCESSING PIPELINE PROFILING")
    print("=" * 70)

    # 1. Profile sample_actions
    print("\n--- sample_actions ---")
    sample_results = profile_sample_actions(batch_sizes, num_actions, device)
    for result in sample_results.values():
        print(f"  {result}")

    # 2. Profile evaluate_actions
    print("\n--- evaluate_actions ---")
    eval_results = profile_evaluate_actions(batch_sizes, num_actions, device)
    for result in eval_results.values():
        print(f"  {result}")

    # 3. Profile log_softmax (component)
    print("\n--- log_softmax (component) ---")
    log_softmax_results = profile_log_softmax(batch_sizes, num_actions, device)
    for result in log_softmax_results.values():
        print(f"  {result}")

    # 4. Profile multinomial sampling (component)
    print("\n--- multinomial sampling (component) ---")
    multinomial_results = profile_multinomial_sampling(batch_sizes, num_actions, device)
    for result in multinomial_results.values():
        print(f"  {result}")

    # 5. Profile entropy computation (component)
    print("\n--- entropy computation (component) ---")
    entropy_results = profile_entropy_computation(batch_sizes, num_actions, device)
    for result in entropy_results.values():
        print(f"  {result}")

    # 6. Profile exp (component)
    print("\n--- exp (component) ---")
    exp_results = profile_exp(batch_sizes, num_actions, device)
    for result in exp_results.values():
        print(f"  {result}")

    # 7. Profile action log-prob indexing (component)
    print("\n--- action log-prob indexing (component) ---")
    indexing_results = profile_action_logprob_indexing(batch_sizes, num_actions, device)
    for result in indexing_results.values():
        print(f"  {result}")

    # 8. Profile GPU-CPU transfer
    if device == "cuda":
        print("\n--- GPU to CPU transfer ---")
        transfer_results = profile_gpu_cpu_transfer(batch_sizes, num_actions)
        for result in transfer_results.values():
            print(f"  {result}")

    # 9. Profile actor head forward
    print("\n--- actor_head forward ---")
    actor_results = profile_actor_head_forward(batch_sizes, hidden_dim, num_actions, device)
    for result in actor_results.values():
        print(f"  {result}")

    # 10. Profile full pipeline
    print("\n--- full pipeline (actor_head + sample_actions) ---")
    pipeline_results = profile_full_pipeline(batch_sizes, hidden_dim, num_actions, device)
    for result in pipeline_results.values():
        print(f"  {result}")

    # Detailed breakdown for a typical batch size
    print("\n" + "=" * 70)
    print("COMPONENT BREAKDOWN (B=4096)")
    print("=" * 70)
    b = 4096
    total = pipeline_results[b].mean_ms
    actor = actor_results[b].mean_ms
    sample = sample_results[b].mean_ms
    log_soft = log_softmax_results[b].mean_ms
    exp = exp_results[b].mean_ms
    multinomial = multinomial_results[b].mean_ms
    indexing = indexing_results[b].mean_ms
    entropy = entropy_results[b].mean_ms
    other_sample = sample - (log_soft + exp + multinomial + indexing + entropy)

    print(f"\nFull pipeline:     {total:.4f}ms (100%)")
    print(f"  Actor head:      {actor:.4f}ms ({100 * actor / total:.1f}%)")
    print(f"  sample_actions:  {sample:.4f}ms ({100 * sample / total:.1f}%)")
    print(f"    - log_softmax: {log_soft:.4f}ms ({100 * log_soft / total:.1f}%)")
    print(f"    - exp:         {exp:.4f}ms ({100 * exp / total:.1f}%)")
    print(f"    - multinomial: {multinomial:.4f}ms ({100 * multinomial / total:.1f}%)")
    print(f"    - log_prob idx:{indexing:.4f}ms ({100 * indexing / total:.1f}%)")
    print(f"    - entropy:     {entropy:.4f}ms ({100 * entropy / total:.1f}%)")
    print(f"    - other:       {other_sample:.4f}ms ({100 * other_sample / total:.1f}%)")

    if device == "cuda":
        transfer = transfer_results[b].mean_ms
        print(f"\nGPU->CPU transfer: {transfer:.4f}ms")

    # Run torch profiler for detailed analysis
    if device == "cuda":
        run_torch_profiler(b, hidden_dim, num_actions, device)

    print("\n" + "=" * 70)
    print("PROFILING COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
