# CPU→GPU Data Transfer Profile

## Executive Summary

This document profiles CPU→GPU data transfer bottlenecks in the MettaGrid training pipeline and provides recommendations
for optimization.

**Mettabox measurement (RTX 4090, 2026-02-10)**:

- Pinned+nonblocking vs unpinned(nonblocking) bandwidth: **26.4 GB/s vs 19.8 GB/s** (script summary: **+33.5%**).
- Example “typical training batch” `(8192, 256)` fp32: **0.3144 ms** pinned+nonblocking vs **0.4243 ms**
  unpinned(nonblocking).

**Key Finding**: The current implementation uses `non_blocking=True` but does NOT use pinned memory. Microbenchmarks
show:

- **Non-blocking** transfers provide **6-49% speedup** over blocking transfers
- **Pinned memory** can provide additional speedup on top of non-blocking (hardware-dependent: ~**1-2%** on the RTX 5080
  laptop microbenchmarks below, but **+33.5%** bandwidth on the RTX 4090 mettabox run above)
- Total potential speedup with both optimizations: **7-50%** vs blocking transfers

**Training SPS Context** (from existing runs and specs):

- **PPO-only training**: ~100k+ SPS (no teacher supervision)
- **Teacher (thinky) training**: ~20k SPS (env-side supervisor overhead)
- **Transfer overhead**: ~2-5% of total training time in `_rollout.td_prep`

The 5x SPS difference between PPO-only and teacher runs is due to scripted teacher inference running in CPU env
processes, not CPU→GPU transfer overhead. Transfer optimizations provide marginal gains compared to addressing the
teacher bottleneck (see [CUDA Scripted Teacher spec](../specs/0010-cuda-scripted-teacher.md)).

## System Configuration

| Property        | Value                              |
| --------------- | ---------------------------------- |
| Device          | NVIDIA GeForce RTX 5080 Laptop GPU |
| CUDA Version    | 12.8                               |
| PyTorch Version | 2.9.0+cu128                        |

## Transfer Microbenchmarks

These benchmarks measure actual CPU→GPU transfer performance for typical training tensor sizes on this hardware.

| Shape                     | Pinned | Non-blocking | Time (ms) | Bandwidth (GB/s) | vs Baseline |
| ------------------------- | ------ | ------------ | --------- | ---------------- | ----------- |
| (1024, 128)\_blocking     | No     | No           | 0.0563    | 9.31             | 1.00x       |
| (1024, 128)\_nonblocking  | No     | Yes          | 0.0377    | 13.91            | 1.49x       |
| (1024, 128)\_pinned       | Yes    | Yes          | 0.0374    | 14.01            | 1.50x       |
| (4096, 128)\_blocking     | No     | No           | 0.1796    | 11.68            | 1.00x       |
| (4096, 128)\_nonblocking  | No     | Yes          | 0.1483    | 14.14            | 1.21x       |
| (4096, 128)\_pinned       | Yes    | Yes          | 0.1466    | 14.31            | 1.23x       |
| (16384, 128)\_blocking    | No     | No           | 0.6486    | 12.93            | 1.00x       |
| (16384, 128)\_nonblocking | No     | Yes          | 0.5937    | 14.13            | 1.09x       |
| (16384, 128)\_pinned      | Yes    | Yes          | 0.5817    | 14.42            | 1.12x       |
| (4096, 256)\_blocking     | No     | No           | 0.3243    | 12.94            | 1.00x       |
| (4096, 256)\_nonblocking  | No     | Yes          | 0.2966    | 14.14            | 1.09x       |
| (4096, 256)\_pinned       | Yes    | Yes          | 0.2917    | 14.38            | 1.11x       |
| (4096, 512)\_blocking     | No     | No           | 0.6509    | 12.89            | 1.00x       |
| (4096, 512)\_nonblocking  | No     | Yes          | 0.5920    | 14.17            | 1.10x       |
| (4096, 512)\_pinned       | Yes    | Yes          | 0.5817    | 14.42            | 1.12x       |
| (8192, 256)\_blocking     | No     | No           | 0.6245    | 13.43            | 1.00x       |
| (8192, 256)\_nonblocking  | No     | Yes          | 0.5906    | 14.20            | 1.06x       |
| (8192, 256)\_pinned       | Yes    | Yes          | 0.5824    | 14.40            | 1.07x       |

## Baseline SPS Measurements

Cogsguard training SPS varies significantly based on configuration. Reference values from existing runs and specs:

| Configuration       | SPS       | Notes                                        |
| ------------------- | --------- | -------------------------------------------- |
| PPO-only (default)  | ~100,000+ | No teacher, pure RL training                 |
| Teacher (thinky BC) | ~20,000   | Scripted teacher runs in CPU env processes   |
| Teacher (CUDA)      | TBD       | Trainer-side CUDA teacher (spec in progress) |

### Configuration Details

Default cogsguard environment (RTX 5080, 12 CPU workers):

```
num_envs=1008, batch_size=504, target_batch_size=512, num_agents=8
policy parameters: 2.82M trainable
```

### Transfer Timing Breakdown

From stopwatch metrics during training:

| Phase                | Fraction | Description                                     |
| -------------------- | -------- | ----------------------------------------------- |
| `_rollout.td_prep`   | ~2-5%    | CPU→GPU transfers (observations, rewards, etc.) |
| `_rollout.env_wait`  | ~10-30%  | Waiting for env step completion                 |
| `_rollout.inference` | ~20-40%  | Policy forward pass                             |
| `_rollout.send`      | ~1-3%    | GPU→CPU action transfer                         |

These percentages shift with configuration. Teacher-supervised runs spend more time in `_rollout.env_wait` due to the
scripted policy running in env processes.

### Running SPS Baseline

To measure baseline SPS on a dedicated GPU:

```bash
# PPO-only baseline (expect ~100k SPS)
./tools/run.py cogsguard.train trainer.total_timesteps=100000

# With teacher (expect ~20k SPS)
./tools/run.py cogsguard.train trainer.total_timesteps=100000 \
    teacher.policy_uri=metta://policy/thinky \
    teacher.mode=scripted.supervisor.mixed
```

Check `timing_per_epoch/sps` in WandB or console output for measured values.

## Current Implementation Analysis

### Transfer Location

The primary CPU→GPU transfers occur in `metta/rl/training/core.py:138-165` within the `_rollout.td_prep` timing context.

### Transfers Per Rollout Step

| Tensor          | Line | Non-blocking | Pinned |
| --------------- | ---- | ------------ | ------ |
| env_obs         | 142  | Yes          | No     |
| rewards         | 144  | Yes          | No     |
| dones           | 163  | Yes          | No     |
| truncateds      | 164  | Yes          | No     |
| teacher_actions | 165  | Yes          | No     |

### GPU→CPU Transfers (Blocking)

| Tensor  | Line | Notes                 |
| ------- | ---- | --------------------- |
| actions | 229  | actions.cpu().numpy() |

### Current Transfer Pattern

```
Environment (CPU) → vectorized env produces observations
    ↓
CoreTrainingLoop.rollout_phase()
    ├─ _rollout.env_wait: Time to get observations from env
    │
    ├─ _rollout.td_prep: ← CPU→GPU TRANSFER HAPPENS HERE
    │   ├─ o.to(device, non_blocking=True)       # observations
    │   ├─ r.to(device, non_blocking=True)       # rewards
    │   ├─ d.to(device, ...)                     # dones
    │   ├─ t.to(device, ...)                     # truncateds
    │   └─ ta.to(device, ...)                    # teacher_actions
    │
    ├─ _rollout.inference: GPU policy forward pass
    │
    └─ _rollout.send: GPU→CPU transfer (actions.cpu())
```

## Optimization Opportunities

### 1. Pinned Memory for Observations (HIGH IMPACT)

**Current**: Observations are created as regular CPU tensors, then transferred with `non_blocking=True`.

**Recommendation**: Allocate observation buffers with `pin_memory=True` in the vectorized environment.

**Expected Speedup**: 1-2% faster transfers on top of non-blocking (which is already used). The bigger win is ensuring
`non_blocking=True` is used consistently.

**Implementation Location**: `metta/rl/training/training_environment.py` or `metta/rl/vecenv.py` where observation
tensors are created.

### 2. Pre-allocated Transfer Buffers (MEDIUM IMPACT)

**Current**: Each transfer call may allocate new GPU memory or temporary buffers.

**Recommendation**: Pre-allocate GPU-side buffers that are reused across steps. This is partially done (experience
buffer is pre-allocated), but the immediate transfer targets could be optimized.

### 3. CUDA Streams for Overlap (LOW IMPACT)

**Current**: All transfers use the default CUDA stream.

**Recommendation**: Use a separate CUDA stream for data transfers to overlap with inference on the default stream.
However, the `non_blocking=True` already provides some overlap.

### 4. Batch GPU→CPU Actions (LOW IMPACT)

**Current**: `actions.cpu().numpy()` is a blocking synchronization point.

**Recommendation**: If latency permits, buffer actions and transfer in larger batches. This trades latency for
throughput.

## Code Locations Reference

| Component         | File                                                             | Key Lines               |
| ----------------- | ---------------------------------------------------------------- | ----------------------- |
| CPU→GPU Transfer  | `metta/rl/training/core.py`                                      | 138-165                 |
| Vectorized Env    | `metta/rl/training/training_environment.py`                      | `get_observations()`    |
| PufferLib Env     | `packages/pufferlib-core/src/pufferlib/vector.py`                | `Multiprocessing` class |
| Experience Buffer | `metta/rl/training/experience.py`                                | `store()`               |
| Stopwatch Timing  | `packages/mettagrid/python/src/mettagrid/profiling/stopwatch.py` | `Stopwatch` class       |

## Conclusions

1. **Current implementation is well-optimized**: The training pipeline already uses `non_blocking=True` for all CPU→GPU
   transfers, which provides 6-49% speedup over blocking transfers.

2. **Pinned memory provides marginal benefit**: Additional 1-2% improvement from pinned memory on top of non-blocking
   transfers. Worth implementing but not a major bottleneck.

3. **Primary bottlenecks are likely elsewhere**: Given that transfers already use non-blocking with 12-14 GB/s
   bandwidth, optimization focus should shift to:
   - Policy inference time (GPU compute)
   - Environment step time (CPU simulation)
   - Reducing synchronization points (e.g., `actions.cpu()`)

## Next Steps

1. **Verify SPS baseline on dedicated hardware**: Run the commands in the "Running SPS Baseline" section above on a
   machine with exclusive GPU access to confirm the ~100k (PPO-only) and ~20k (teacher) reference values.

2. **Profile specific phases**: If `_rollout.td_prep` is >10% of wall time, consider implementing pinned memory for
   observation buffers.

3. **Investigate teacher bottleneck**: The 5x SPS difference between PPO-only and teacher runs is the primary
   optimization target. See the [CUDA Scripted Teacher spec](../specs/0010-cuda-scripted-teacher.md) for the proposed
   solution to move teacher inference to GPU.

4. **Investigate other bottlenecks**: Use torch profiler to identify GPU compute bottlenecks in policy inference.

## Appendix: Running Full Training Profile

To get detailed timing breakdown during training:

```bash
# Run training with torch profiler enabled
TORCH_PROFILER_FIRST_EPOCH=1 ./tools/run.py cogsguard.train \
    trainer.total_timesteps=5000000 \
    torch_profiler.interval_epochs=1 \
    torch_profiler.profile_dir=./profiler_output
```

The Stopwatch metrics (visible in logs and WandB) will show:

- `timing_per_epoch/frac/_rollout.td_prep`: Fraction of time in CPU→GPU transfers
- `timing_per_epoch/frac/_rollout.env_wait`: Fraction of time waiting for observations
- `timing_per_epoch/frac/_rollout.inference`: Fraction of time in policy forward pass
- `timing_per_epoch/frac/_rollout.send`: Fraction of time sending actions to environment
- `timing_per_epoch/sps`: Steps per second for the epoch

## Appendix: Profiling Script

A dedicated profiling script is available at `tests/perf/profile_cpu_gpu_transfer.py`:

```bash
uv run tests/perf/profile_cpu_gpu_transfer.py
```

This runs transfer microbenchmarks and regenerates this report with updated hardware-specific data.
