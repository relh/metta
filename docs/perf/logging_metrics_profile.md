# Logging and Metrics Overhead Profile

This document analyzes the performance overhead of logging and metrics collection during metta training.

## Overview

The training pipeline includes several logging and metrics components that add overhead to training throughput (SPS -
steps per second):

| Component         | Location                | Frequency                |
| ----------------- | ----------------------- | ------------------------ |
| WandB logging     | `stats_reporter.py:237` | Per epoch                |
| ProgressLogger    | `progress_logger.py`    | Per epoch                |
| Stats computation | `stats.py`              | Per step + per epoch     |
| System monitoring | `monitor.py`            | Continuous (1s sampling) |
| Memory monitoring | `monitor.py`            | Per epoch                |

## Architecture

### Logging Call Flow

```
Training Loop (trainer.py)
    │
    ├─ _rollout phase ────────────────────────────────────────┐
    │   └─ on_step() callbacks                                 │
    │       └─ StatsReporter.accumulate_infos()               │
    │           └─ accumulate_rollout_stats() ◄───────────────┤ Overhead #1
    │                                                          │
    ├─ _train phase                                            │
    │                                                          │
    └─ _epoch_end callbacks                                    │
        ├─ StatsReporter.report_epoch()                       │
        │   ├─ process_training_stats() ◄─────────────────────┤ Overhead #2
        │   ├─ compute_timing_stats()                          │
        │   ├─ build_wandb_payload() ◄────────────────────────┤ Overhead #3
        │   └─ wandb_run.log() ◄──────────────────────────────┤ Overhead #4
        │                                                      │
        └─ ProgressLogger.on_epoch_end()                      │
            └─ log_training_progress() ◄──────────────────────┤ Overhead #5
                └─ log_rich_progress() [if TTY]
```

### Key Files

| File                                       | Purpose                                |
| ------------------------------------------ | -------------------------------------- |
| `metta/rl/stats.py`                        | Core stats accumulation and processing |
| `metta/rl/training/stats_reporter.py`      | WandB payload building and logging     |
| `metta/rl/training/progress_logger.py`     | Console progress output                |
| `metta/rl/training/monitor.py`             | System and memory monitoring           |
| `common/src/metta/common/wandb/context.py` | WandB connection management            |

## Overhead Analysis

### 1. Stats Accumulation (`accumulate_rollout_stats`)

**Location:** `metta/rl/stats.py:18-50`

**Called:** Every training step (high frequency)

**Operations:**

- Iterates through info dictionaries from all environments
- Detaches tensors from GPU (potential GPU sync)
- Converts tensors to CPU scalars
- Unrolls nested dictionaries
- Extends lists for accumulation

**Overhead factors:**

- Tensor detach/CPU transfer for each metric
- `unroll_nested_dict()` recursion
- List extension operations

```python
# Hot path from stats.py:28-30
if torch.is_tensor(v):
    v = v.detach().cpu().item() if v.numel() == 1 else v.detach().cpu().numpy()
```

### 2. Stats Processing (`process_training_stats`)

**Location:** `metta/rl/stats.py:88-142`

**Called:** Every epoch (at stats_reporter interval)

**Operations:**

- Computes `np.mean()` on all accumulated lists
- Builds environment stats dictionary
- Filters movement metrics
- Computes overview statistics

**Overhead factors:**

- O(n) mean computation for each metric
- Dictionary comprehensions and filtering
- Memory allocation for processed stats

### 3. WandB Payload Building (`build_wandb_payload`)

**Location:** `metta/rl/training/stats_reporter.py:41-92`

**Called:** Every epoch (at stats_reporter interval)

**Operations:**

- Converts all stats to scalars (`_to_scalar`)
- Builds flattened dictionary with prefixes
- Handles tensor conversion edge cases
- Computes rolling averages

**Overhead factors:**

- Scalar conversion for 100+ metrics
- String formatting for metric keys
- Rolling average deque operations

### 4. WandB Network I/O (`wandb.log`)

**Location:** `metta/rl/training/stats_reporter.py:237`

**Called:** Every epoch (at stats_reporter interval)

**Operations:**

- JSON serialization of payload
- HTTP POST to api.wandb.ai
- Response handling

**Overhead factors:**

- Network latency (typically 50-200ms)
- Payload serialization (100+ metrics)
- Potential blocking on network I/O

### 5. Console Logging (`log_training_progress`)

**Location:** `metta/rl/training/progress_logger.py:90-151`

**Called:** Every epoch

**Operations:**

- Computes time percentages and SPS
- Formats large numbers with SI units
- Renders Rich table (if TTY)
- Writes to console

**Overhead factors:**

- Rich table rendering (if enabled)
- String formatting operations
- Console I/O

### 6. System Monitoring

**Location:** `metta/rl/training/monitor.py`

**Called:** Continuously (1-second sampling interval)

**Operations:**

- CPU utilization tracking
- Memory usage monitoring
- GPU metrics (if available)

**Overhead factors:**

- Background thread overhead
- System call overhead for metrics
- Memory allocation for history

## Profiling Script

A profiling script is available at `tests/perf/profile_logging_overhead.py` that patches key functions to measure
timing:

```bash
# Run with default settings
uv run python tests/perf/profile_logging_overhead.py --epochs 5

# Disable wandb for baseline comparison
uv run python tests/perf/profile_logging_overhead.py --disable-wandb --epochs 5

# Output to JSON
uv run python tests/perf/profile_logging_overhead.py --output results.json
```

## Benchmark Results

> **Note:** Fill in these sections with actual benchmark data from GPU runs.

### Baseline SPS (Logging Enabled)

| Configuration     | SPS | Notes          |
| ----------------- | --- | -------------- |
| cogsguard default | TBD | Full logging   |
| cogsguard sandbox | TBD | Reduced config |

### SPS with Logging Disabled

| Configuration            | SPS | Delta vs Baseline |
| ------------------------ | --- | ----------------- |
| wandb disabled           | TBD | TBD               |
| stats_reporter disabled  | TBD | TBD               |
| console logging disabled | TBD | TBD               |

### Component Overhead Breakdown

| Component                | Time/Epoch (ms) | % of Epoch Time |
| ------------------------ | --------------- | --------------- |
| wandb.log                | TBD             | TBD             |
| accumulate_rollout_stats | TBD             | TBD             |
| process_training_stats   | TBD             | TBD             |
| build_wandb_payload      | TBD             | TBD             |
| log_training_progress    | TBD             | TBD             |
| System/Memory monitoring | TBD             | TBD             |

## Recommendations

### High-Impact Optimizations

1. **Batch WandB Logging**
   - Current: Log every epoch
   - Recommendation: Consider logging every N epochs for long runs
   - Config: `stats_reporter.interval` (default: 1)

2. **Reduce Metric Count**
   - Current: 100+ metrics per log call
   - Recommendation: Filter environment metrics more aggressively
   - Location: `filter_movement_metrics()` in `stats.py`

3. **Async WandB Logging**
   - Current: Synchronous HTTP POST
   - Recommendation: WandB already uses async internally, but network latency still affects the main thread
   - Mitigation: Use `wandb.Settings(quiet=True)` (already enabled)

### Medium-Impact Optimizations

4. **Lazy Tensor Detach**
   - Current: Detach all tensors immediately
   - Recommendation: Accumulate tensor references, detach in batch at epoch end
   - Trade-off: Memory vs CPU overhead

5. **Disable Console Progress for Long Runs**
   - Current: Rich table rendering every epoch
   - Recommendation: Use simple logging for non-interactive runs
   - Config: Set `TERM=dumb` or disable TTY detection

6. **Reduce System Monitor Sampling**
   - Current: 1-second sampling interval
   - Recommendation: 5-10 second sampling for production runs
   - Location: `monitor.py` SystemMonitor initialization

### Low-Impact Optimizations

7. **Pre-allocate Stats Dictionaries**
   - Current: `defaultdict(list)` with dynamic allocation
   - Recommendation: Pre-size based on expected metrics

8. **Use NumPy for Batch Mean**
   - Current: `np.mean(list)` per metric
   - Recommendation: Already using NumPy, minimal improvement available

## Configuration Options

### Disable WandB

```python
# In recipe or TrainTool config
wandb=WandbConfig.Off()
```

Or via environment:

```bash
WANDB_MODE=disabled python tools/run.py ...
```

### Reduce Stats Interval

```python
# In TrainTool config
stats_reporter=StatsReporterConfig(interval=5)  # Log every 5 epochs
```

### Disable Console Progress

The ProgressLogger automatically uses simple logging when not connected to a TTY:

```python
# In progress_logger.py:118
if should_use_rich_console():
    log_rich_progress(...)
else:
    logger.info(message)  # Simple text logging
```

## Conclusion

Based on code analysis, the primary sources of logging overhead are:

1. **WandB network I/O** - Synchronous HTTP calls to api.wandb.ai
2. **Tensor CPU transfer** - `detach().cpu().item()` calls in hot path
3. **Stats serialization** - Building and flattening 100+ metrics

For production runs prioritizing SPS:

- Increase `stats_reporter.interval` to reduce logging frequency
- Consider disabling WandB for pure training speed tests
- Filter unnecessary environment metrics

The profiling script in `tests/perf/profile_logging_overhead.py` can be used to measure actual overhead on your hardware
configuration.
