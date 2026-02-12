# Logging Follow-Up 2: Streaming Stats Aggregation (No Per-Step List Growth)

## Area

`#6907` Logging/metrics

## Hypothesis

Accumulating raw per-step lists then computing epoch means causes avoidable Python/object overhead. Streaming
aggregators (count/sum/min/max) should lower CPU and memory pressure.

## Proposed Change

Replace list accumulation in rollout stats with streaming metric accumulators; compute epoch stats from accumulator
state directly.

## Code Touch Points

- `metta/rl/stats.py` (`accumulate_rollout_stats`, `process_training_stats`)
- `metta/rl/training/stats_reporter.py`

## Benchmark Plan

1. Baseline current stats accumulation on same workload.
2. Variant with streaming aggregation only.
3. Measure:

- `_process_stats` wall time
- peak memory for stats structures
- metric value parity (within tolerance)

## Success Criteria

- > = 25% lower `_process_stats` CPU time
- > = 30% lower stats-memory footprint
- metric parity for core logged values

## Guardrails

- Preserve metric names and schema.
- Keep unsupported non-numeric metrics explicitly dropped (current behavior).
