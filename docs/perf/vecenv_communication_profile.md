# Vectorized Environment Communication Profile

This document profiles the communication overhead in PufferLib's vectorized environment implementation with MettaGrid
(cogsguard recipe).

**Date**: 2026-02-10 **Hardware**: 12-core CPU, NVIDIA GPU **Environment**: cogsguard, 8 agents per env, max_steps=1000

## Executive Summary

| Backend           | Envs | Workers | Agent SPS | Speedup | Notes                  |
| ----------------- | ---- | ------- | --------- | ------- | ---------------------- |
| Serial (baseline) | 1    | 1       | 72,240    | 1.0x    | Single env baseline    |
| Serial            | 8    | 1       | 80,422    | 1.11x   | 8 envs, single process |
| Multiprocessing   | 8    | 4       | 94,782    | 1.31x   | Best config tested     |
| Multiprocessing   | 12   | 12      | 93,216    | 1.29x   | Diminishing returns    |

**Key Findings:**

1. **IPC overhead is minimal**: Shared memory (RawArray) eliminates serialization costs
2. **Synchronization is the bottleneck**: 98%+ of step time is spent waiting in `recv()`
3. **Parallel efficiency is ~30%**: 4 workers yield 1.18x speedup over 1 worker
4. **Optimal config**: 4-8 workers for 8-agent environments

## 1. Architecture Overview

### PufferLib Multiprocessing Flow

```
Main Process                    Worker Processes
     │                               │
     ├─── send(actions) ────────────►│ Write to shared memory
     │         │                     │
     │    semaphore = STEP ─────────►│ Worker polls semaphore
     │                               │
     │                               │ env.step(actions)
     │                               │ Write obs/rewards to shared memory
     │                               │
     │◄─── semaphore = MAIN ─────────┤ Worker signals ready
     │                               │
     ├─── recv() ───────────────────►│ Read from shared memory
     │    (polls semaphores)         │
     │    (collects from pipes)      │
     ▼                               ▼
```

### Key Components

| Component         | Location                      | Purpose                         |
| ----------------- | ----------------------------- | ------------------------------- |
| `Multiprocessing` | `pufferlib/vector.py:254-547` | Process pool with shared memory |
| `Serial`          | `pufferlib/vector.py:56-183`  | Single-process vectorization    |
| `_worker_process` | `pufferlib/vector.py:185-252` | Worker loop (semaphore polling) |
| `make_vecenv`     | `metta/rl/vecenv.py:52-102`   | MettaGrid vecenv factory        |

## 2. IPC Overhead Analysis

### Shared Memory Structure

PufferLib uses `multiprocessing.RawArray` for zero-copy data sharing:

```python
self.shm = dict(
    observations=RawArray(obs_ctype, num_agents * obs_size),  # ~38 KB for 64 agents
    actions=RawArray(atn_ctype, num_agents * atn_size),
    rewards=RawArray("f", num_agents),
    terminals=RawArray("b", num_agents),
    truncateds=RawArray("b", num_agents),
    teacher_actions=RawArray(atn_ctype, num_agents * atn_size),
    masks=RawArray("b", num_agents),
    semaphores=RawArray("c", num_workers),
    notify=RawArray("b", num_workers),
)
```

**Measured Memory Usage:**

| Data Type    | Size per Agent | Total (64 agents) |
| ------------ | -------------- | ----------------- |
| Observations | 600 bytes      | 38,400 bytes      |
| Actions      | 4 bytes        | 256 bytes         |
| Rewards      | 4 bytes        | 256 bytes         |
| Terminals    | 1 byte         | 64 bytes          |
| **Total**    | ~609 bytes     | **~39 KB**        |

### IPC Timing Breakdown

From profiling 8 envs with 4 workers:

| Operation      | Mean Time | % of Step | Notes                  |
| -------------- | --------- | --------- | ---------------------- |
| `recv()`       | 0.66 ms   | 98.3%     | Polling + pipe reads   |
| `send()`       | 0.003 ms  | 0.4%      | Write to shared memory |
| **Total step** | 0.67 ms   | 100%      |                        |

**Observation**: The `send()` operation is effectively instant because it only:

1. Writes actions to a pre-allocated shared memory buffer
2. Sets semaphore flags to signal workers

The `recv()` dominates because it must:

1. Poll all worker semaphores until batch_size workers are ready
2. Receive info dicts via pipes (for non-empty info)
3. Reshape/view shared memory arrays

## 3. Serialization Costs

### What Gets Serialized

| Data          | Serialization        | Notes                  |
| ------------- | -------------------- | ---------------------- |
| Observations  | None (shared memory) | Zero-copy via RawArray |
| Actions       | None (shared memory) | Zero-copy via RawArray |
| Rewards/Dones | None (shared memory) | Zero-copy via RawArray |
| Info dicts    | Pickle via Pipe      | Only if non-empty      |
| Seeds (reset) | Pickle via Pipe      | Once per reset         |

**Serialization is minimal** because:

- Core data (obs/actions/rewards) uses shared memory
- Only metadata (info dicts) uses pipes
- MettaGrid returns empty info for most steps

### Memory Copy Analysis

With `zero_copy=True` (default):

- Contiguous worker blocks return views directly into shared memory
- No memory copies for observation gathering

With `zero_copy=False`:

- Non-contiguous worker results are gathered and copied
- Additional latency but allows for more flexible scheduling

## 4. Process Synchronization

### Semaphore-Based Coordination

Workers poll a semaphore array in a tight loop:

```python
while True:
    sem = semaphores[worker_idx]
    if sem >= MAIN:
        if time.time() - start > 0.5:
            time.sleep(0.01)  # Avoid CPU spin
        continue

    if sem == STEP:
        _, _, _, _, infos = envs.step(atn_arr)
    # ...
```

### Synchronization Bottleneck

**Problem**: The main process must wait for the _slowest_ worker in each batch.

**Evidence**: High step time variance (553-640%) indicates workers finish at different times.

```
Step time statistics (8 envs, 4 workers):
  Mean:  0.67 ms
  P50:   0.24 ms  (median is much lower than mean)
  P95:   0.70 ms
  P99:   5.53 ms
  Max:  73.13 ms  (occasional GC or system pauses)
```

The large gap between P50 (0.24 ms) and mean (0.67 ms) shows that most steps complete quickly, but outliers drag down
throughput.

### Synchronization Modes

PufferLib supports two modes via `sync_traj`:

1. **Synchronized** (`sync_traj=True`, default):
   - Waits for workers in order
   - Maintains trajectory ordering
   - Lower throughput but deterministic

2. **Async** (`sync_traj=False`):
   - Returns first batch_size ready workers
   - Higher throughput but reordered trajectories
   - May cause training instability

## 5. Subprocess Spawning Overhead

### Process Creation

Worker processes are created once during `Multiprocessing.__init__`:

```python
for i in range(num_workers):
    p = Process(target=_worker_process, args=(...))
    p.start()
```

**Measured startup cost**: Not profiled separately, but:

- Python Process spawn: ~50-100 ms per worker
- Worker environment creation: ~200-500 ms per worker
- Total initial overhead: ~1-2 seconds for 12 workers

This is amortized over the entire training run (millions of steps).

### Worker Process Overhead

Each worker process:

- Has its own Python interpreter
- Loads the full MettaGrid simulation
- Maintains its own GIL (no contention with main process)

Memory overhead per worker: ~100-200 MB additional RSS.

## 6. Shared Memory Benefits

### Memory Efficiency

| Approach                | Memory per Agent      | For 64 Agents   |
| ----------------------- | --------------------- | --------------- |
| Shared Memory (current) | 609 bytes             | 39 KB           |
| Pickle serialization    | 600+ bytes + overhead | 50+ KB per step |
| Direct copy             | 609 bytes + buffers   | 78+ KB          |

**Bandwidth savings**: At 95k agent-steps/s with 600-byte observations:

- Shared memory: 0 bytes copied (views only)
- Without shared memory: ~54 MB/s of copies

### Zero-Copy Observation Gathering

With zero_copy enabled:

```python
o = buf["observations"][w_slice].reshape(self.obs_batch_shape)
```

This returns a view, not a copy. The shared memory is directly accessible as a NumPy array with zero overhead.

## 7. Async Stepping Analysis

### Current Behavior

PufferLib steps environments **synchronously** within each batch:

1. `send()` signals all workers in the batch
2. Workers step in parallel (true concurrency)
3. `recv()` waits for all workers to complete

### Async Stepping Trade-offs

| Mode           | Throughput | Ordering  | Training Stability |
| -------------- | ---------- | --------- | ------------------ |
| Sync (current) | Lower      | Preserved | Stable             |
| Async          | Higher     | Reordered | May vary           |

**Potential optimization**: Double-buffering with async stepping could hide more latency, but would complicate
trajectory management.

## 8. Optimization Recommendations

### 1. Worker Count Tuning

Based on profiling, optimal configuration is **1 worker per 2 environments**:

| Envs | Optimal Workers | Rationale               |
| ---- | --------------- | ----------------------- |
| 4    | 2-4             | Balance sync overhead   |
| 8    | 4               | Best tested config      |
| 16   | 8               | Avoid over-subscription |

### 2. Reduce Info Dict Overhead

Currently, info dicts are sent via pipes. For steps with empty info, this adds overhead. Consider:

- Batching info across multiple steps
- Using shared memory for common info fields

### 3. Batch Size Alignment

Ensure `batch_size` divides evenly by `workers_per_batch`:

```python
workers_per_batch = batch_size // (num_envs // num_workers)
```

Misalignment causes fallback to non-zero-copy paths.

### 4. Consider Larger Batches

Larger batch sizes amortize synchronization overhead:

- 64 agents: 0.67 ms/step = ~10.5 μs/agent
- 128 agents: Would amortize to ~5-7 μs/agent

### 5. GC Tuning

Observed P99 latency spikes (73 ms) suggest garbage collection. Consider:

- `gc.disable()` during critical sections
- Pre-allocating all buffers at startup

## 9. Success Criteria Checklist

- [x] Baseline SPS recorded (cogsguard, GPU): ~80k-95k agent-SPS
- [x] IPC overhead as % of step time: ~0.4% (send) + 98% (recv waiting)
- [x] Synchronization bottlenecks identified: Worker variance, semaphore polling
- [x] 3 optimization recommendations:
  1. Tune workers to 1 per 2 envs
  2. Reduce info dict overhead
  3. Align batch sizes for zero-copy

## Appendix: Profiling Script

The profiling script is located at `tests/perf/profile_vecenv_communication.py`.

Usage:

```bash
# Compare backends
uv run python tests/perf/profile_vecenv_communication.py --vectorization compare

# Profile specific config
uv run python tests/perf/profile_vecenv_communication.py \
    --vectorization multiprocessing \
    --num-envs 16 \
    --num-workers 8 \
    --duration 30

# Output JSON
uv run python tests/perf/profile_vecenv_communication.py --output results.json
```

## Appendix: Raw Profile Data

```json
{
  "serial": {
    "agent_sps": 80422.28,
    "step_mean_ms": 0.7945,
    "recv_mean_ms": 0.0006,
    "send_mean_ms": 0.7892
  },
  "multiprocessing": {
    "agent_sps": 94782.48,
    "step_mean_ms": 0.6736,
    "recv_mean_ms": 0.6621,
    "send_mean_ms": 0.0028
  }
}
```
