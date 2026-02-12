# Logging Follow-Up 1: Async WandB Queue + Background Flush

## Area

`#6907` Logging/metrics

## Hypothesis

Synchronous `wandb.log` in the training thread adds network-driven stalls. A bounded async queue with background flush
should reduce stats-phase wall time.

## Proposed Change

Move WandB emission off the training hot path: training thread enqueues payloads, background worker batches and flushes.

## Code Touch Points

- `metta/rl/training/stats_reporter.py`
- `metta/rl/training/wandb_logger.py`
- `common/src/metta/common/wandb/context.py`

## Benchmark Plan

1. Baseline with current synchronous logging.
2. Variant with async queue only.
3. Measure:

- `_process_stats` time/epoch
- agent-SPS
- dropped/late metric count

## Success Criteria

- > = 20% reduction in `_process_stats` time
- > = 3% agent-SPS improvement
- zero metric loss at normal run rates

## Guardrails

- Bounded queue with explicit backpressure policy.
- Flush remaining metrics on shutdown/failure.
