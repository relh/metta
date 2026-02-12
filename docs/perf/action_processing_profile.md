# Action Processing Pipeline Performance Profile

**Date**: 2026-02-10 **Hardware**: NVIDIA GeForce RTX 5080 Laptop GPU (16GB VRAM) **CUDA Version**: 12.8 **Test
Environment**: CogsGuard with 21 discrete actions

## Executive Summary

The action processing pipeline in Metta's RL training loop is **highly optimized** and is **NOT a bottleneck** in the
overall training throughput. The pipeline can process ~63M samples/second, vastly exceeding typical training
requirements.

The primary bottleneck within the action pipeline is `torch.multinomial` sampling, which accounts for ~48% of pipeline
time. However, since the pipeline itself takes only ~0.16ms per batch, this is not a concern for practical training
scenarios.

## Baseline Measurements

| Metric                           | Value                  |
| -------------------------------- | ---------------------- |
| Environment-only SPS (no policy) | 243,095                |
| Action pipeline throughput       | 62,871,993 samples/sec |
| Pipeline time per batch (B=8192) | 0.130ms                |

## Component Timing Breakdown (Batch Size = 4096)

| Component           | Time (ms) | % of Pipeline |
| ------------------- | --------- | ------------- |
| **Full pipeline**   | 0.156     | 100%          |
| Actor head (linear) | 0.047     | 30.1%         |
| sample_actions      | 0.158     | 101.2%\*      |
| - log_softmax       | 0.010     | 6.2%          |
| - multinomial       | 0.075     | **47.8%**     |
| - entropy           | 0.019     | 12.3%         |
| GPU->CPU transfer   | 0.016     | 10.3%         |

\*Note: sample_actions includes async GPU operations measured separately from the full pipeline.

## Scaling Analysis

### sample_actions by Batch Size

| Batch Size | Time (ms) | Throughput (M samples/sec) |
| ---------- | --------- | -------------------------- |
| 256        | 0.165     | 1.6                        |
| 512        | 0.140     | 3.7                        |
| 1024       | 0.131     | 7.8                        |
| 2048       | 0.143     | 14.3                       |
| 4096       | 0.158     | 25.9                       |
| 8192       | 0.137     | 59.8                       |

**Observation**: Time scales sub-linearly with batch size, demonstrating good GPU utilization. Larger batches are more
efficient per sample.

### evaluate_actions by Batch Size

| Batch Size | Time (ms) |
| ---------- | --------- |
| 256        | 0.029     |
| 512        | 0.046     |
| 1024       | 0.042     |
| 2048       | 0.045     |
| 4096       | 0.063     |
| 8192       | 0.058     |

**Observation**: `evaluate_actions` is ~3x faster than `sample_actions` because it doesn't perform stochastic sampling
(no multinomial call).

## Key Bottleneck: torch.multinomial

The `torch.multinomial` operation dominates action sampling time:

- Takes 0.075ms at B=4096 (47.8% of pipeline)
- Requires random number generation on GPU
- Cannot be easily optimized without changing the sampling strategy

### Why This Matters (And Why It Doesn't)

**Why it matters**: For real-time inference (e.g., game playing), multinomial sampling adds latency to every action
decision.

**Why it doesn't matter for training**: At 62M samples/second, the action pipeline processes a typical batch faster than
the environment can generate new observations. Training is bottlenecked by:

1. Environment stepping (243k SPS)
2. Backbone network forward pass
3. PPO loss computation and backward pass

## torch.compile Optimization

Both `sample_actions` and `evaluate_actions` use `torch.compile()` for optimization. The torch profiler shows the
compiled kernels are highly efficient:

```
triton_per_fused__log_softmax_exp_mul_neg_prepare_so...    2.530ms (444 calls) = 5.7us/call
```

The fused kernel combines log_softmax, exp, multiplication, and negation into a single CUDA launch, minimizing kernel
launch overhead.

## Architecture-Specific Notes

### Current Implementation

- **Discrete actions only**: Uses `Categorical` distribution via multinomial
- **21 action space**: CogsGuard environment
- **Action masking**: Masks actions beyond index 21 with large negative logits

### Code Locations

| Component        | File                                                     |
| ---------------- | -------------------------------------------------------- |
| sample_actions   | `agent/src/metta/agent/util/distribution_utils.py:9-41`  |
| evaluate_actions | `agent/src/metta/agent/util/distribution_utils.py:44-75` |
| ActorHead        | `agent/src/metta/agent/components/actor.py:212-265`      |
| ActionProbs      | `agent/src/metta/agent/components/actor.py:116-198`      |

## Optimization Recommendations

### 1. Consider Gumbel-Softmax for Differentiable Sampling

**Impact**: Low (action pipeline not a bottleneck) **Effort**: Medium

Replace multinomial with Gumbel-Softmax during training for fully differentiable action selection. This could enable
end-to-end gradient flow and eliminate the multinomial call, but may affect exploration behavior.

### 2. Batch Action Transfers to CPU

**Impact**: Low (0.016ms per batch) **Effort**: Low

Currently, actions are transferred to CPU per batch. If multiple batches could be grouped before CPU transfer (e.g., for
vectorized environments), this overhead could be amortized. However, at 0.016ms this is not a significant concern.

### 3. Pre-compute Log Probabilities During Rollout

**Impact**: Medium (for training phase) **Effort**: Low

Store full_log_probs during rollout (already done) to avoid recomputing during PPO updates. The current implementation
already does this efficiently. No changes needed.

### 4. Fused Multinomial-Log-Prob Kernel (Advanced)

**Impact**: High (for inference latency) **Effort**: High

Write a custom CUDA kernel that fuses:

- log_softmax computation
- multinomial sampling
- log probability extraction for sampled action

This would eliminate multiple kernel launches and memory round-trips. Only worthwhile for real-time inference where
sub-millisecond latency matters.

## Conclusion

The action processing pipeline is well-optimized and represents a minor fraction of overall training time. The
`torch.compile` optimization provides efficient fused kernels, and the architecture scales well with batch size.

**Priority for optimization should focus elsewhere**:

1. Environment stepping throughput
2. Backbone network efficiency
3. Loss computation and gradient accumulation

The profiling script at `tests/perf/profile_action_pipeline.py` can be re-run to measure performance on different
hardware or after code changes.
